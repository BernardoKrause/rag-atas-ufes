from __future__ import annotations

import logging

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.item_pauta import ItemPauta
from app.recuperacao.fusao import ancorar, fundir_rrf
from app.recuperacao.grafo import expandir_grafo, obter_contexto_grafo
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
    hits_lexico = _com_degradacao("lexico", buscar_lexico, pergunta, sessao) or []
    hits_vetorial = _com_degradacao("vetorial", buscar_vetorial, pergunta, cliente_qdrant) or []

    ancoras = ancorar(hits_lexico, hits_vetorial, top_n=top_n_ancora)
    hits_grafo = _com_degradacao("expansao_grafo", expandir_grafo, ancoras, driver) or []

    ids_finais = fundir_rrf(hits_lexico, hits_vetorial, hits_grafo, k=k)
    if not ids_finais:
        return []

    itens_por_id = {
        item.item_id_canonico: item
        for item in sessao.execute(
            select(ItemPauta).where(ItemPauta.item_id_canonico.in_(ids_finais))
        ).scalars()
    }
    score_lexico = {hit.item_id_canonico: hit.score for hit in hits_lexico}
    score_vetorial = {hit.item_id_canonico: hit.score for hit in hits_vetorial}
    score_grafo = {hit.item_id_canonico: hit.score for hit in hits_grafo}

    evidencias = []
    for rank, item_id in enumerate(ids_finais, start=1):
        item = itens_por_id.get(item_id)
        if item is None:
            continue
        evidencias.append(
            Evidencia(
                item_id_canonico=item_id,
                texto=item.texto,
                contexto_grafo=_com_degradacao("contexto_grafo", obter_contexto_grafo, item_id, driver) or {},
                rank_final=rank,
                scores={
                    "lexico": score_lexico.get(item_id),
                    "vetorial": score_vetorial.get(item_id),
                    "grafo": score_grafo.get(item_id),
                },
            )
        )
    return evidencias


def _com_degradacao(nome_camada, funcao, *args):
    try:
        return funcao(*args)
    except Exception:
        logger.warning("camada %s falhou, seguindo sem ela", nome_camada, exc_info=True)
        return None
