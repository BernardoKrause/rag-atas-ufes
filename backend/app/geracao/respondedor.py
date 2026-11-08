from __future__ import annotations

import logging
from datetime import date

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.geracao.contexto import montar_contexto
from app.geracao.eventos import interpretar_eventos, ler_resposta_direta, montar_texto
from app.geracao.llm import ClienteLLM
from app.geracao.prompt import (
    ESQUEMA_EVENTOS,
    ESQUEMA_RESPOSTA,
    FRASE_ABSTENCAO,
    SISTEMA_RESPOSTA,
    montar_prompt,
)
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
    saida = cliente_llm.gerar(sistema, usuario, esquema=ESQUEMA_EVENTOS)
    if saida.truncada:
        logger.warning("resposta do LLM truncada por max_tokens")
    if FRASE_ABSTENCAO.rstrip(".") in saida.texto:
        return RespostaDetalhada(_abstencao(), numeradas, saida)

    datas = {e.numero: e.data_reuniao or date.min for e in numeradas}
    eventos = interpretar_eventos(saida.texto, datas)
    if eventos is None:
        logger.warning("resposta do LLM não é um JSON de eventos válido")
        return RespostaDetalhada(_abstencao(), numeradas, saida)
    if not eventos:
        return RespostaDetalhada(_abstencao(), numeradas, saida)
    citados = {evento.evidencia for evento in eventos}
    _, usuario_resposta = montar_prompt(pergunta, [e for e in numeradas if e.numero in citados])
    saida_resposta = cliente_llm.gerar(SISTEMA_RESPOSTA, usuario_resposta, esquema=ESQUEMA_RESPOSTA)
    if saida_resposta.truncada:
        logger.warning("resposta direta do LLM truncada por max_tokens")
    fontes = [e.fonte for e in numeradas if e.numero in citados]
    texto = montar_texto(eventos, datas, ler_resposta_direta(saida_resposta.texto))
    resposta = Resposta(texto=texto, fontes=fontes, abstencao=False)
    return RespostaDetalhada(resposta, numeradas, saida, saida_resposta)


def responder(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    cliente_llm: ClienteLLM,
) -> Resposta:
    return responder_detalhado(pergunta, sessao, cliente_qdrant, driver, cliente_llm).resposta
