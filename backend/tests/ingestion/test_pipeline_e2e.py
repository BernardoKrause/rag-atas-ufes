from datetime import date
from pathlib import Path

import pytest

import app.ingestion.pipeline as pipeline_module
from app.ingestion.collector import AtaParaProcessar
from app.ingestion.pipeline import executar_pipeline, processar_ata
from app.models.documento import Documento

FIXTURES = Path(__file__).parent.parent / "fixtures" / "atas_sample"
SECRET_KEY = b"chave-de-teste-nao-usar-em-producao"


def test_pipeline_processa_as_6_variantes_estruturais(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY, db_session)

    assert len(documentos) == 6
    assert {d.nome_arquivo for d in documentos} == {
        "ata_da_1a_reuniao_ordinaria_-_db_ccens_04-02-2025.docx.pdf",
        "ata_05_02_2025.pdf",
        "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf",
        "10-2025.pdf",
        "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf",
        "ata_da_3a_reuniao_ordinaria_colped.pdf",
    }
    assert all(d.id_documento is not None for d in documentos)
    assert all(len(d.texto_limpo) > 100 for d in documentos)


def test_pipeline_preenche_campos_organizacionais_e_estruturais(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY, db_session)
    por_arquivo = {d.nome_arquivo: d for d in documentos}

    ccae = por_arquivo["1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf"]
    assert ccae.centro == "CCAE"
    assert ccae.tipo_orgao == "B"
    assert ccae.numero_reuniao == 1
    assert ccae.tipo_reuniao == "Ordinaria"
    assert ccae.horario_inicio == "14:00"
    assert ccae.modalidade == "Presencial"


def test_pipeline_aceita_orgaos_sem_numero_ou_carater_de_reuniao(db_session):
    # CAR nao numera atas na fonte e nao declara carater (ordinaria/extraordinaria)
    documentos = executar_pipeline(FIXTURES, SECRET_KEY, db_session)
    car = next(d for d in documentos if d.nome_arquivo == "ata_05_02_2025.pdf")

    assert car.numero_reuniao is None
    assert car.tipo_reuniao is None
    assert car.centro == "CAR"


def test_reprocessar_o_corpus_e_idempotente(db_session):
    executar_pipeline(FIXTURES, SECRET_KEY, db_session)
    documentos = executar_pipeline(FIXTURES, SECRET_KEY, db_session)

    assert len(documentos) == 6
    assert db_session.query(Documento).count() == 6


def test_atas_de_orgaos_diferentes_com_mesmo_nome_de_arquivo_nao_colidem(db_session):
    # regressao: processar_ata identificava o documento so por nome_arquivo,
    # entao duas atas de orgaos diferentes com o mesmo nome de arquivo
    # colapsavam na mesma linha e a segunda sobrescrevia a primeira
    pdf_ccae = (
        FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CCAE"
        / "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf"
    )
    pdf_ct = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CT" / "10-2025.pdf"

    ata_ccae = AtaParaProcessar(
        tipo="TIPO_B", orgao="CCAE", numero_reuniao=1, caratere="Ordinaria",
        data_reuniao=date(2025, 1, 28), arquivo="mesmo_nome.pdf", caminho_pdf=pdf_ccae,
    )
    ata_ct = AtaParaProcessar(
        tipo="TIPO_B", orgao="CT", numero_reuniao=10, caratere="",
        data_reuniao=date(2025, 6, 27), arquivo="mesmo_nome.pdf", caminho_pdf=pdf_ct,
    )

    doc_ccae = processar_ata(ata_ccae, SECRET_KEY, db_session)
    doc_ct = processar_ata(ata_ct, SECRET_KEY, db_session)

    assert doc_ccae.id_documento != doc_ct.id_documento
    assert doc_ccae.centro == "CCAE"
    assert doc_ct.centro == "CT"
    assert db_session.query(Documento).filter_by(nome_arquivo="mesmo_nome.pdf").count() == 2


def test_falha_no_meio_do_lote_preserva_atas_ja_processadas(db_session, monkeypatch):
    # regressao: executar_pipeline so commitava uma vez, no final; uma ata
    # com falha no meio do corpus descartava (via rollback implicito) todas
    # as atas ja processadas com sucesso na mesma execucao
    pdf_ccae = (
        FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CCAE"
        / "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf"
    )
    ata_boa = AtaParaProcessar(
        tipo="TIPO_B", orgao="CCAE", numero_reuniao=1, caratere="Ordinaria",
        data_reuniao=date(2025, 1, 28), arquivo="boa.pdf", caminho_pdf=pdf_ccae,
    )
    ata_com_pdf_inexistente = AtaParaProcessar(
        tipo="TIPO_B", orgao="CT", numero_reuniao=2, caratere="Ordinaria",
        data_reuniao=date(2025, 2, 1), arquivo="ruim.pdf",
        caminho_pdf=FIXTURES / "nao_existe.pdf",
    )
    monkeypatch.setattr(
        pipeline_module, "coletar_atas", lambda _: [ata_boa, ata_com_pdf_inexistente]
    )

    # extrair_texto_bruto usa pymupdf, cuja excecao de arquivo ausente e uma
    # classe propria (pymupdf.FileNotFoundError), nao o FileNotFoundError do
    # builtins — so importa que algo falhe, nao qual excecao especificamente
    with pytest.raises(Exception):
        executar_pipeline(Path("caminho-nao-usado"), SECRET_KEY, db_session)

    assert db_session.query(Documento).filter_by(nome_arquivo="boa.pdf").count() == 1
    assert db_session.query(Documento).filter_by(nome_arquivo="ruim.pdf").count() == 0
