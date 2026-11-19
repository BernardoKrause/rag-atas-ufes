from __future__ import annotations

import logging

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from app.recuperacao.fusao import ancorar, pontuar_rrf
from app.recuperacao.grafo import expandir_grafo, obter_contextos_grafo, rastrear_expansao
from app.recuperacao.lexico import buscar_lexico
from app.recuperacao.setor import documentos_do_orgao, identificar_orgao
from app.recuperacao.tipos import Evidencia, Hit
from app.recuperacao.vetorial import buscar_vetorial

logger = logging.getLogger(__name__)

K_PADRAO = 5
TOP_N_ANCORA_PADRAO = 10
CAMADAS_TODAS = frozenset({"lexico", "vetorial", "grafo", "campos_grafo"})


def recuperar(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    k: int = K_PADRAO,
    top_n_ancora: int = TOP_N_ANCORA_PADRAO,
    camadas: frozenset[str] = CAMADAS_TODAS,
    registro: dict | None = None,
) -> list[Evidencia]:
    if camadas - CAMADAS_TODAS or not camadas & {"lexico", "vetorial"}:
        raise ValueError(f"camadas inválidas: {sorted(camadas)}")

    falhas: list[str] = []
    orgao = identificar_orgao(pergunta, sessao)
    documentos = documentos_do_orgao(orgao, sessao) if orgao else None

    hits_lexico = []
    if "lexico" in camadas:
        hits_lexico = (
            _com_degradacao(
                "lexico", buscar_lexico, pergunta, sessao, orgao=orgao, sessao=sessao, falhas=falhas
            ) or []
        )
    hits_vetorial = []
    if "vetorial" in camadas:
        hits_vetorial = (
            _com_degradacao(
                "vetorial", buscar_vetorial, pergunta, cliente_qdrant, documentos=documentos, falhas=falhas
            ) or []
        )

    ancoras, hits_grafo, hits_grafo_sem_filtro = [], [], []
    if "grafo" in camadas:
        ancoras = ancorar(hits_lexico, hits_vetorial, top_n=top_n_ancora)
        hits_grafo_sem_filtro = (
            _com_degradacao("expansao_grafo", expandir_grafo, ancoras, driver, falhas=falhas) or []
        )
        hits_grafo = _so_do_orgao(hits_grafo_sem_filtro, orgao, sessao) if orgao else hits_grafo_sem_filtro

    pontuados = pontuar_rrf(hits_lexico, hits_vetorial, hits_grafo)
    ids_finais = [linha["item_id_canonico"] for linha in pontuados[:k]]

    itens_por_id = {}
    if ids_finais:
        itens_por_id = (
            _com_degradacao(
                "hidratacao_itens", _buscar_itens_por_id, sessao, ids_finais, sessao=sessao, falhas=falhas
            ) or {}
        )
    score_lexico = {hit.item_id_canonico: hit.score for hit in hits_lexico}
    score_vetorial = {hit.item_id_canonico: hit.score for hit in hits_vetorial}
    score_grafo = {hit.item_id_canonico: hit.score for hit in hits_grafo}

    itens_encontrados = [item_id for item_id in ids_finais if item_id in itens_por_id]
    contextos_grafo = {}
    if "campos_grafo" in camadas and itens_encontrados:
        contextos_grafo = (
            _com_degradacao(
                "contexto_grafo", obter_contextos_grafo, itens_encontrados, driver, falhas=falhas
            ) or {}
        )

    if registro is not None:
        registro.update({
            "camadas": sorted(camadas),
            "k": k,
            "top_n_ancora": top_n_ancora,
            "orgao": orgao,
            "documentos_do_orgao": len(documentos) if documentos is not None else None,
            "lexico": _hits(hits_lexico),
            "vetorial": _hits(hits_vetorial),
            "ancoras": _hits(ancoras),
            "grafo_antes_do_filtro": _hits(hits_grafo_sem_filtro),
            "grafo": _hits(hits_grafo),
            "caminhos_grafo": (
                _com_degradacao("caminhos_grafo", rastrear_expansao, ancoras, driver, falhas=falhas) or []
                if ancoras else []
            ),
            "fusao": pontuados,
            "ids_finais": ids_finais,
            "ids_sem_item": [item_id for item_id in ids_finais if item_id not in itens_por_id],
            "contextos_grafo": contextos_grafo,
            "falhas": falhas,
        })

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


def _hits(hits: list[Hit]) -> list[dict]:
    return [{"item_id_canonico": hit.item_id_canonico, "rank": hit.rank, "score": hit.score} for hit in hits]


def _buscar_itens_por_id(sessao: Session, ids_finais: list[str]) -> dict[str, ItemPauta]:
    return {
        item.item_id_canonico: item
        for item in sessao.execute(
            select(ItemPauta).where(ItemPauta.item_id_canonico.in_(ids_finais))
        ).scalars()
    }


def _com_degradacao(nome_camada, funcao, *args, sessao=None, falhas=None, **kwargs):
    try:
        if sessao is None:
            return funcao(*args, **kwargs)
        # savepoint: um erro real de SQL (nao so o RuntimeError sintetico dos
        # testes) deixa a transacao da sessao abortada; sem isolar num
        # savepoint, a proxima chamada que toca a mesma sessao (ex.
        # hidratacao final) falha em cascata mesmo com as outras camadas
        # saudaveis.
        with sessao.begin_nested():
            return funcao(*args, **kwargs)
    except Exception:
        logger.warning("camada %s falhou, seguindo sem ela", nome_camada, exc_info=True)
        if falhas is not None:
            falhas.append(nome_camada)
        return None


def _so_do_orgao(hits: list[Hit], orgao: str, sessao: Session) -> list[Hit]:
    if not hits:
        return []
    permitidos = set(sessao.execute(
        select(ItemPauta.item_id_canonico)
        .join(Documento, ItemPauta.documento_id == Documento.id_documento)
        .where(Documento.orgao == orgao, ItemPauta.item_id_canonico.in_([hit.item_id_canonico for hit in hits]))
    ).scalars())
    return [hit for hit in hits if hit.item_id_canonico in permitidos]
