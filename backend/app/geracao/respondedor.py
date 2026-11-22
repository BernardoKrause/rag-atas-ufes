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
from app.recuperacao.orquestrador import CAMADAS_TODAS, K_PADRAO, recuperar

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
    k: int = K_PADRAO,
    registro: dict | None = None,
    orgao: str | None = None,
) -> RespostaDetalhada:
    rastreio_recuperacao = {} if registro is not None else None
    evidencias = recuperar(
        pergunta, sessao, cliente_qdrant, driver, k=k, camadas=camadas, registro=rastreio_recuperacao,
        orgao=orgao,
    )
    numeradas = montar_contexto(evidencias, sessao) if evidencias else []
    chamadas: list[dict] = []
    if registro is not None:
        registro.update({
            "recuperacao": rastreio_recuperacao,
            "contexto": [_contexto_enviado(e) for e in numeradas],
            "chamadas_eventos": chamadas,
            "chamada_resposta": None,
            "desfechos_anexados": {},
            "texto_final": None,
        })
    if not numeradas:
        return _finalizar(registro, RespostaDetalhada(_abstencao(), [], []))

    eventos, saidas = [], []
    for evidencia in numeradas:
        sistema, usuario = montar_prompt(pergunta, [evidencia])
        saida = _gerar(cliente_llm, sistema, usuario, ESQUEMA_EVENTOS, "resposta do LLM truncada por max_tokens")
        saidas.append(saida)
        interpretados, situacao = _eventos(saida, evidencia)
        apoiados, descartados = _separar_apoiados(pergunta, interpretados, evidencia)
        eventos += apoiados
        chamadas.append({
            "evidencia": evidencia.numero,
            **_chamada(sistema, usuario, saida),
            "situacao": situacao,
            "eventos_aceitos": [_evento(e) for e in apoiados],
            "eventos_descartados": [{**_evento(e), "termos_sem_apoio": termos} for e, termos in descartados],
        })
    if not eventos:
        return _finalizar(registro, RespostaDetalhada(_abstencao(), numeradas, saidas))

    datas = {e.numero: e.data_reuniao or date.min for e in numeradas}
    eventos.sort(key=lambda evento: datas[evento.evidencia])
    sistema_resposta, usuario_resposta = montar_prompt_resposta(pergunta, eventos, numeradas)
    saida_resposta = _gerar(
        cliente_llm, sistema_resposta, usuario_resposta, ESQUEMA_RESPOSTA,
        "resposta direta do LLM truncada por max_tokens",
    )
    citados = {evento.evidencia for evento in eventos}
    fontes = [e.fonte for e in numeradas if e.numero in citados]
    desfechos = {e.numero: desfecho_registrado(e.frases_grafo) for e in numeradas}
    resposta_direta = ler_resposta_direta(saida_resposta.texto, eventos)
    texto = montar_texto(eventos, datas, resposta_direta, desfechos)
    if registro is not None:
        registro["chamada_resposta"] = {
            **_chamada(sistema_resposta, usuario_resposta, saida_resposta),
            "resposta_direta_aceita": resposta_direta,
        }
        registro["desfechos_anexados"] = {
            str(numero): desfecho for numero, desfecho in desfechos.items() if numero in citados and desfecho
        }
    resposta = Resposta(texto=texto, fontes=fontes, abstencao=False)
    return _finalizar(registro, RespostaDetalhada(resposta, numeradas, saidas, saida_resposta))


def _finalizar(registro: dict | None, detalhada: RespostaDetalhada) -> RespostaDetalhada:
    if registro is not None:
        registro["texto_final"] = detalhada.resposta.texto
        registro["abstencao"] = detalhada.resposta.abstencao
        registro["fontes"] = [fonte.item_id_canonico for fonte in detalhada.resposta.fontes]
    return detalhada


def _gerar(cliente_llm: ClienteLLM, sistema: str, usuario: str, esquema: dict, aviso: str) -> SaidaLLM:
    saida = cliente_llm.gerar(sistema, usuario, esquema=esquema)
    if saida.truncada:
        logger.warning(aviso)
    return saida


def _chamada(sistema: str, usuario: str, saida: SaidaLLM) -> dict:
    return {
        "sistema": sistema,
        "usuario": usuario,
        "saida_bruta": saida.texto,
        "truncada": saida.truncada,
        "tokens_entrada": saida.tokens_entrada,
        "tokens_saida": saida.tokens_saida,
    }


def _evento(evento: Evento) -> dict:
    return {"evidencia": evento.evidencia, "descricao": evento.descricao}


def _contexto_enviado(evidencia: EvidenciaNumerada) -> dict:
    return {
        "numero": evidencia.numero,
        "item_id_canonico": evidencia.fonte.item_id_canonico,
        "documento_id": evidencia.fonte.documento_id,
        "rotulo": evidencia.fonte.rotulo,
        "pagina": evidencia.fonte.pagina,
        "data_reuniao": evidencia.data_reuniao.isoformat() if evidencia.data_reuniao else None,
        "texto": evidencia.texto,
        "frases_grafo": evidencia.frases_grafo,
        "assunto_anterior": evidencia.assunto_anterior,
        "assunto_posterior": evidencia.assunto_posterior,
    }


def _eventos(saida: SaidaLLM, evidencia: EvidenciaNumerada) -> tuple[list[Evento], str]:
    if FRASE_ABSTENCAO.rstrip(".") in saida.texto:
        return [], "abstencao"
    eventos = interpretar_eventos(saida.texto, {evidencia.numero: evidencia.data_reuniao or date.min})
    if eventos is None:
        logger.warning("resposta do LLM não é um JSON de eventos válido")
        return [], "json_invalido"
    return eventos, "ok"


def _separar_apoiados(
    pergunta: str, eventos: list[Evento], evidencia: EvidenciaNumerada
) -> tuple[list[Evento], list[tuple[Evento, list[str]]]]:
    fonte = f"{evidencia.texto} {evidencia.fonte.rotulo}"
    apoiados, descartados = [], []
    for evento in eventos:
        sem_apoio = termos_sem_apoio(evento.descricao, pergunta, fonte)
        if sem_apoio:
            logger.info("evento da evidência %d descartado: %s fora do trecho", evento.evidencia, sem_apoio)
            descartados.append((evento, sem_apoio))
        else:
            apoiados.append(evento)
    return apoiados, descartados


def responder(
    pergunta: str,
    sessao: Session,
    cliente_qdrant: QdrantClient,
    driver: Driver,
    cliente_llm: ClienteLLM,
    orgao: str | None = None,
) -> Resposta:
    return responder_detalhado(pergunta, sessao, cliente_qdrant, driver, cliente_llm, orgao=orgao).resposta
