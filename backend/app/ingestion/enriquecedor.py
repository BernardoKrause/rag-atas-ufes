from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


@dataclass(frozen=True)
class CamposEnriquecidos:
    assunto: str | None
    tipo_desfecho: str | None
    resultado_votacao: str | None
    encaminhamento: str | None
    ato_emitido: str | None
    departamento_origem: str | None


CONFIG_ENRIQUECEDOR: dict[tuple[str, str], Callable[[str, date], CamposEnriquecidos]] = {}


def _obter_extrator(tipo_orgao: str, centro: str) -> Callable[[str, date], CamposEnriquecidos]:
    if (tipo_orgao, centro) in CONFIG_ENRIQUECEDOR:
        return CONFIG_ENRIQUECEDOR[(tipo_orgao, centro)]
    if (tipo_orgao, "*") in CONFIG_ENRIQUECEDOR:
        return CONFIG_ENRIQUECEDOR[(tipo_orgao, "*")]
    raise ValueError(f"variante sem extrator mapeado: tipo_orgao={tipo_orgao!r} centro={centro!r}")


def enriquecer_item(tipo_orgao: str, centro: str, item_texto: str, data_reuniao: date) -> CamposEnriquecidos:
    extrator = _obter_extrator(tipo_orgao, centro)
    return extrator(item_texto, data_reuniao)


def enriquecer_e_persistir(documento: Documento, itens: list[ItemPauta], sessao: Session) -> None:
    for item in itens:
        campos = enriquecer_item(documento.tipo_orgao, documento.centro, item.texto, documento.data_reuniao)
        item.assunto = campos.assunto
        item.tipo_desfecho = campos.tipo_desfecho
        item.resultado_votacao = campos.resultado_votacao
        item.encaminhamento = campos.encaminhamento
        item.ato_emitido = campos.ato_emitido
        item.departamento_origem = campos.departamento_origem
    sessao.flush()


def main() -> None:
    engine = create_engine(settings.database_url)
    Sessao = sessionmaker(bind=engine)

    with Sessao() as sessao:
        documentos = sessao.execute(select(Documento)).scalars().all()
        total_itens = 0
        for documento in documentos:
            itens = sessao.execute(
                select(ItemPauta).where(ItemPauta.documento_id == documento.id_documento)
            ).scalars().all()
            enriquecer_e_persistir(documento, itens, sessao)
            sessao.commit()
            total_itens += len(itens)
        print(f"{len(documentos)} documentos processados, {total_itens} itens enriquecidos.")


if __name__ == "__main__":
    main()
