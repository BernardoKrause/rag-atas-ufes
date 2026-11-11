from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento import Documento

RE_SETOR = re.compile(r"\bno setor\s+(\w+(?:\s*/\s*\w+)*)", re.IGNORECASE)


def identificar_orgao(pergunta: str, sessao: Session) -> str | None:
    match = RE_SETOR.search(pergunta)
    if not match:
        return None
    chave = "_".join(re.split(r"\s*/\s*", match.group(1))).upper()
    orgaos = sessao.execute(select(Documento.orgao).distinct()).scalars()
    return next((orgao for orgao in orgaos if orgao.upper() == chave), None)


def documentos_do_orgao(orgao: str, sessao: Session) -> list[int]:
    return list(sessao.execute(select(Documento.id_documento).where(Documento.orgao == orgao)).scalars())
