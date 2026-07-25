from pathlib import Path

from app.ingestion.pipeline import executar_pipeline
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
