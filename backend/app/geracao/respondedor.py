from __future__ import annotations

import logging

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.geracao.citacoes import processar_citacoes
from app.geracao.contexto import montar_contexto
from app.geracao.llm import ClienteLLM
from app.geracao.prompt import FRASE_ABSTENCAO, montar_prompt
from app.geracao.tipos import Resposta, RespostaDetalhada
from app.recuperacao.orquestrador import CAMADAS_TODAS, recuperar

logger = logging.getLogger(__name__)


def _abstencao() -> Resposta:
    return Resposta(texto=FRASE_ABSTENCAO, fontes=[], abstencao=True)


def responder_detalhado(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    cliente_llm: ClienteLLM,
    camadas: frozenset[str] = CAMADAS_TODAS,
) -> RespostaDetalhada:
    evidencias = recuperar(pergunta, sessao, cliente_qdrant, driver, camadas=camadas)
    numeradas = montar_contexto(evidencias, sessao) if evidencias else []
    if not numeradas:
        return RespostaDetalhada(_abstencao(), [], None)

    sistema, usuario = montar_prompt(pergunta, numeradas)
    saida = cliente_llm.gerar(sistema, usuario)
    if saida.truncada:
        logger.warning("resposta do LLM truncada por max_tokens")
    if FRASE_ABSTENCAO.rstrip(".") in saida.texto:
        return RespostaDetalhada(_abstencao(), numeradas, saida)

    texto, citados = processar_citacoes(saida.texto, {e.numero for e in numeradas})
    if not citados:
        return RespostaDetalhada(_abstencao(), numeradas, saida)
    fontes = [e.fonte for e in numeradas if e.numero in citados]
    return RespostaDetalhada(Resposta(texto=texto, fontes=fontes, abstencao=False), numeradas, saida)


def responder(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    cliente_llm: ClienteLLM,
) -> Resposta:
    return responder_detalhado(pergunta, sessao, cliente_qdrant, driver, cliente_llm).resposta
