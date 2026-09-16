from __future__ import annotations

import logging

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.item_pauta import ItemPauta
from app.recuperacao.fusao import ancorar, fundir_rrf
from app.recuperacao.grafo import expandir_grafo, obter_contextos_grafo
from app.recuperacao.lexico import buscar_lexico
from app.recuperacao.tipos import Evidencia
from app.recuperacao.vetorial import buscar_vetorial

logger = logging.getLogger(__name__)

K_PADRAO = 5
TOP_N_ANCORA_PADRAO = 10


def recuperar(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    k: int = K_PADRAO,
    top_n_ancora: int = TOP_N_ANCORA_PADRAO,
) -> list[Evidencia]:
    hits_lexico = _com_degradacao("lexico", buscar_lexico, pergunta, sessao, sessao=sessao) or []
    hits_vetorial = _com_degradacao("vetorial", buscar_vetorial, pergunta, cliente_qdrant) or []

    ancoras = ancorar(hits_lexico, hits_vetorial, top_n=top_n_ancora)
    hits_grafo = _com_degradacao("expansao_grafo", expandir_grafo, ancoras, driver) or []

    ids_finais = fundir_rrf(hits_lexico, hits_vetorial, hits_grafo, k=k)
    if not ids_finais:
        return []

    itens_por_id = (
        _com_degradacao("hidratacao_itens", _buscar_itens_por_id, sessao, ids_finais, sessao=sessao) or {}
    )
    score_lexico = {hit.item_id_canonico: hit.score for hit in hits_lexico}
    score_vetorial = {hit.item_id_canonico: hit.score for hit in hits_vetorial}
    score_grafo = {hit.item_id_canonico: hit.score for hit in hits_grafo}

    itens_encontrados = [item_id for item_id in ids_finais if item_id in itens_por_id]
    contextos_grafo = (
        _com_degradacao("contexto_grafo", obter_contextos_grafo, itens_encontrados, driver) or {}
    )

    evidencias = []
    for rank, item_id in enumerate(itens_encontrados, start=1):
        item = itens_por_id[item_id]
        evidencias.append(
            Evidencia(
                item_id_canonico=item_id,
                texto=item.texto,
                contexto_grafo=contextos_grafo.get(item_id, {}),
                rank_final=rank,
                scores={
                    "lexico": score_lexico.get(item_id),
                    "vetorial": score_vetorial.get(item_id),
                    "grafo": score_grafo.get(item_id),
                },
            )
        )
    return evidencias


def _buscar_itens_por_id(sessao: Session, ids_finais: list[str]) -> dict[str, ItemPauta]:
    return {
        item.item_id_canonico: item
        for item in sessao.execute(
            select(ItemPauta).where(ItemPauta.item_id_canonico.in_(ids_finais))
        ).scalars()
    }


def _com_degradacao(nome_camada, funcao, *args, sessao=None):
    try:
        if sessao is None:
            return funcao(*args)
        # savepoint: um erro real de SQL (nao so o RuntimeError sintetico dos
        # testes) deixa a transacao da sessao abortada; sem isolar num
        # savepoint, a proxima chamada que toca a mesma sessao (ex.
        # hidratacao final) falha em cascata mesmo com as outras camadas
        # saudaveis.
        with sessao.begin_nested():
            return funcao(*args)
    except Exception:
        logger.warning("camada %s falhou, seguindo sem ela", nome_camada, exc_info=True)
        return None
