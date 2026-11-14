from __future__ import annotations

import logging
from datetime import date

from neo4j import Driver
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.geracao.contexto import montar_contexto
from app.geracao.eventos import (
    Evento,
    desfecho_registrado,
    interpretar_eventos,
    ler_resposta_direta,
    montar_texto,
    termos_sem_apoio,
)
from app.geracao.llm import ClienteLLM
from app.geracao.prompt import (
    ESQUEMA_EVENTOS,
    ESQUEMA_RESPOSTA,
    FRASE_ABSTENCAO,
    montar_prompt,
    montar_prompt_resposta,
)
from app.geracao.tipos import EvidenciaNumerada, Resposta, RespostaDetalhada, SaidaLLM
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
        return RespostaDetalhada(_abstencao(), [], [])

    eventos, saidas = [], []
    for evidencia in numeradas:
        saida = _avaliar(pergunta, evidencia, cliente_llm)
        saidas.append(saida)
        eventos += _eventos_apoiados(pergunta, _eventos(saida, evidencia), evidencia)
    if not eventos:
        return RespostaDetalhada(_abstencao(), numeradas, saidas)

    datas = {e.numero: e.data_reuniao or date.min for e in numeradas}
    eventos.sort(key=lambda evento: datas[evento.evidencia])
    sistema_resposta, usuario_resposta = montar_prompt_resposta(pergunta, eventos, numeradas)
    saida_resposta = cliente_llm.gerar(sistema_resposta, usuario_resposta, esquema=ESQUEMA_RESPOSTA)
    if saida_resposta.truncada:
        logger.warning("resposta direta do LLM truncada por max_tokens")
    citados = {evento.evidencia for evento in eventos}
    fontes = [e.fonte for e in numeradas if e.numero in citados]
    desfechos = {e.numero: desfecho_registrado(e.frases_grafo) for e in numeradas}
    texto = montar_texto(eventos, datas, ler_resposta_direta(saida_resposta.texto, eventos), desfechos)
    resposta = Resposta(texto=texto, fontes=fontes, abstencao=False)
    return RespostaDetalhada(resposta, numeradas, saidas, saida_resposta)


def _avaliar(pergunta: str, evidencia: EvidenciaNumerada, cliente_llm: ClienteLLM) -> SaidaLLM:
    sistema, usuario = montar_prompt(pergunta, [evidencia])
    saida = cliente_llm.gerar(sistema, usuario, esquema=ESQUEMA_EVENTOS)
    if saida.truncada:
        logger.warning("resposta do LLM truncada por max_tokens")
    return saida


def _eventos(saida: SaidaLLM, evidencia: EvidenciaNumerada) -> list[Evento]:
    if FRASE_ABSTENCAO.rstrip(".") in saida.texto:
        return []
    eventos = interpretar_eventos(saida.texto, {evidencia.numero: evidencia.data_reuniao or date.min})
    if eventos is None:
        logger.warning("resposta do LLM não é um JSON de eventos válido")
        return []
    return eventos


def _eventos_apoiados(pergunta: str, eventos: list[Evento], evidencia: EvidenciaNumerada) -> list[Evento]:
    fonte = f"{evidencia.texto} {evidencia.fonte.rotulo}"
    apoiados = []
    for evento in eventos:
        sem_apoio = termos_sem_apoio(evento.descricao, pergunta, fonte)
        if sem_apoio:
            logger.info("evento da evidência %d descartado: %s fora do trecho", evento.evidencia, sem_apoio)
        else:
            apoiados.append(evento)
    return apoiados


def responder(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    cliente_llm: ClienteLLM,
) -> Resposta:
    return responder_detalhado(pergunta, sessao, cliente_qdrant, driver, cliente_llm).resposta
