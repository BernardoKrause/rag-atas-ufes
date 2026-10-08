from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.grafo import construtor
from app.ingestion import enriquecedor, indexador, pipeline, segmentador
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def _descrever(documento: Documento) -> str:
    return f"{documento.id_documento} {documento.orgao} {documento.nome_arquivo}"


def executar_etapas(etapas: list[tuple[str, Callable[[], None]]]) -> None:
    for nome, etapa in etapas:
        print(f"== {nome}")
        etapa()


def resumir_corpus(sessao: Session) -> dict:
    documentos = sessao.execute(select(Documento).order_by(Documento.id_documento)).scalars().all()
    ids_com_itens = set(sessao.execute(select(ItemPauta.documento_id).distinct()).scalars())
    return {
        "documentos": len(documentos),
        "itens": sessao.execute(select(func.count()).select_from(ItemPauta)).scalar_one(),
        "documentos_com_ocr": [_descrever(d) for d in documentos if d.paginas_ocr],
        "documentos_sem_item": [_descrever(d) for d in documentos if d.id_documento not in ids_com_itens],
    }


def main() -> None:
    executar_etapas([
        ("ingestao", pipeline.main),
        ("segmentacao", segmentador.main),
        ("enriquecimento", enriquecedor.main),
        ("indexacao", indexador.main),
        ("grafo", construtor.main),
    ])

    engine = create_engine(settings.database_url)
    with sessionmaker(bind=engine)() as sessao:
        resumo = resumir_corpus(sessao)

    print(f"{resumo['documentos']} documentos, {resumo['itens']} itens.")
    print(f"{len(resumo['documentos_com_ocr'])} documentos com OCR:")
    for linha in resumo["documentos_com_ocr"]:
        print(f"  {linha}")
    print(f"{len(resumo['documentos_sem_item'])} documentos sem item:")
    for linha in resumo["documentos_sem_item"]:
        print(f"  {linha}")


if __name__ == "__main__":
    main()
