from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def mapa_item_logico(sessao: Session) -> dict[str, str]:
    linhas = sessao.execute(
        select(
            ItemPauta.item_id_canonico, ItemPauta.documento_id, ItemPauta.secao,
            ItemPauta.numero_item, ItemPauta.ocorrencia_indice, ItemPauta.fragmento_indice,
        )
    ).all()

    def chave(linha):
        return (linha.documento_id, linha.secao, linha.numero_item, linha.ocorrencia_indice or 0)

    principal = {
        chave(linha): linha.item_id_canonico for linha in linhas if not linha.fragmento_indice
    }
    return {
        linha.item_id_canonico: principal.get(chave(linha), linha.item_id_canonico)
        for linha in linhas
    }


def descrever_itens(sessao: Session, ids: Iterable[str]) -> dict[str, dict]:
    linhas = sessao.execute(
        select(ItemPauta, Documento)
        .join(Documento, Documento.id_documento == ItemPauta.documento_id)
        .where(ItemPauta.item_id_canonico.in_(list(ids)))
    ).all()
    return {
        item.item_id_canonico: {
            "orgao": documento.orgao,
            "data_reuniao": documento.data_reuniao.isoformat(),
            "numero_reuniao": documento.numero_reuniao,
            "assunto": item.assunto,
            "texto": item.texto,
            "pagina_inicio": item.pagina_inicio,
        }
        for item, documento in linhas
    }
