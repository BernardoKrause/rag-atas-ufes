from datetime import date

import pytest

from app.ingestion import completa
from app.ingestion.completa import executar_etapas, resumir_corpus
from app.ingestion.extractor import TesseractAusenteError
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def test_executar_etapas_roda_na_ordem():
    chamadas = []
    etapas = [(nome, lambda nome=nome: chamadas.append(nome)) for nome in ("a", "b", "c")]

    executar_etapas(etapas)

    assert chamadas == ["a", "b", "c"]


def test_executar_etapas_para_na_primeira_falha():
    chamadas = []

    def _falha():
        raise RuntimeError("etapa quebrou")

    etapas = [("a", lambda: chamadas.append("a")), ("b", _falha), ("c", lambda: chamadas.append("c"))]

    with pytest.raises(RuntimeError, match="etapa quebrou"):
        executar_etapas(etapas)

    assert chamadas == ["a"]


def _documento(nome_arquivo: str, paginas_ocr: list[int]) -> Documento:
    return Documento(
        nome_arquivo=nome_arquivo, url_origem=nome_arquivo, centro="CEUNES", campus="São Mateus",
        tipo_orgao="A", orgao="TESTE_RESUMO", data_reuniao=date(2025, 1, 1), texto_limpo="texto",
        paginas_ocr=paginas_ocr,
    )


def test_resumir_corpus_lista_documentos_sem_item_e_com_ocr(db_session):
    sem_item = _documento("sem_item.pdf", [1, 2])
    com_item = _documento("com_item.pdf", [])
    db_session.add_all([sem_item, com_item])
    db_session.flush()
    db_session.add(ItemPauta(
        documento_id=com_item.id_documento, item_id_canonico="TESTE_RESUMO_1", secao="PAUTA",
        numero_item="1", texto="x",
    ))
    db_session.flush()

    resumo = resumir_corpus(db_session)

    assert f"{sem_item.id_documento} TESTE_RESUMO sem_item.pdf" in resumo["documentos_sem_item"]
    assert f"{com_item.id_documento} TESTE_RESUMO com_item.pdf" not in resumo["documentos_sem_item"]
    assert f"{sem_item.id_documento} TESTE_RESUMO sem_item.pdf" in resumo["documentos_com_ocr"]
    assert resumo["documentos"] >= 2
    assert resumo["itens"] >= 1


def test_main_verifica_o_tesseract_antes_da_primeira_etapa(monkeypatch):
    chamadas = []

    def _sem_tesseract():
        raise TesseractAusenteError("sem tesseract")

    monkeypatch.setattr(completa, "verificar_tesseract", _sem_tesseract)
    monkeypatch.setattr(completa, "executar_etapas", chamadas.append)

    with pytest.raises(TesseractAusenteError):
        completa.main()

    assert chamadas == []
