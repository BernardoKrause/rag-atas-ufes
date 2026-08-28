from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def carregar_documentos_com_itens(sessao: Session) -> list[tuple[Documento, list[ItemPauta]]]:
    documentos = sessao.execute(select(Documento).order_by(Documento.id_documento)).scalars().all()
    return [
        (
            documento,
            sessao.execute(
                select(ItemPauta)
                .where(ItemPauta.documento_id == documento.id_documento)
                .order_by(ItemPauta.id)
            ).scalars().all(),
        )
        for documento in documentos
    ]
