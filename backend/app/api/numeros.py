from __future__ import annotations

import re
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.geracao.tipos import Resposta
from app.ingestion.cleaner import RE_NUMERO_PROCESSO
from app.models.documento import NumeroProcesso

RE_TOKEN_PROCESSO = re.compile(r"PROCESSO_\d{4,}")


def revelar_na_resposta(resposta: Resposta, sessao: Session) -> Resposta:
    textos = [resposta.texto, *(fonte.trecho for fonte in resposta.fontes)]
    tokens = {token for texto in textos for token in RE_TOKEN_PROCESSO.findall(texto)}
    if not tokens:
        return resposta
    numeros = dict(sessao.execute(
        select(NumeroProcesso.token, NumeroProcesso.numero).where(NumeroProcesso.token.in_(tokens))
    ).all())

    def revelar(texto: str) -> str:
        return RE_TOKEN_PROCESSO.sub(lambda m: numeros.get(m.group(), m.group()), texto)

    return replace(
        resposta,
        texto=revelar(resposta.texto),
        fontes=[replace(fonte, trecho=revelar(fonte.trecho)) for fonte in resposta.fontes],
    )


def ocultar_numeros(pergunta: str, sessao: Session) -> str:
    def ocultar(match: re.Match) -> str:
        numero = "".join(match.group().split())
        token = sessao.scalar(select(NumeroProcesso.token).where(NumeroProcesso.numero == numero))
        return token or match.group()

    return RE_NUMERO_PROCESSO.sub(ocultar, pergunta)
