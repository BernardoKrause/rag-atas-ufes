from datetime import date

import pytest

from app.ingestion.collector import coletar_atas

CSV_HEADER = "tipo;orgao;numero_reuniao;caratere;data;arquivo;status\n"


def _montar_corpus(tmp_path, linhas_csv, criar_pdfs=True):
    corpus_path = tmp_path / "ATAS_UFES"
    corpus_path.mkdir()
    (tmp_path / "inventario_atas.csv").write_text(CSV_HEADER + linhas_csv, encoding="utf-8-sig")

    if criar_pdfs:
        for linha in linhas_csv.strip().splitlines():
            tipo, orgao, _, _, _, arquivo, status = linha.split(";")
            if status != "presente":
                continue
            pasta = corpus_path / f"{tipo}__Pasta_Qualquer" / orgao
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / arquivo).touch()

    return corpus_path


def test_coleta_apenas_atas_com_status_presente(tmp_path):
    linhas = (
        "TIPO_A;CCENS_DB;1;Ordinaria;2025-02-04;ata_1.pdf;presente\n"
        "TIPO_A;CCENS_DB;2;Ordinaria;2025-03-04;ata_2.pdf;ausente\n"
    )
    corpus_path = _montar_corpus(tmp_path, linhas)

    atas = coletar_atas(corpus_path)

    assert len(atas) == 1
    assert atas[0].arquivo == "ata_1.pdf"


def test_resolve_caminho_pdf_por_tipo_e_orgao(tmp_path):
    linhas = "TIPO_B;CAR;3;Ordinaria;2025-05-10;ata_3.pdf;presente\n"
    corpus_path = _montar_corpus(tmp_path, linhas)

    atas = coletar_atas(corpus_path)

    assert atas[0].caminho_pdf == corpus_path / "TIPO_B__Pasta_Qualquer" / "CAR" / "ata_3.pdf"
    assert atas[0].caminho_pdf.is_file()


def test_converte_numero_reuniao_e_data(tmp_path):
    linhas = "TIPO_A;CCENS_DB;7;Ordinaria;2025-06-15;ata_7.pdf;presente\n"
    corpus_path = _montar_corpus(tmp_path, linhas)

    atas = coletar_atas(corpus_path)

    assert atas[0].numero_reuniao == 7
    assert atas[0].data_reuniao == date(2025, 6, 15)


def test_numero_reuniao_nulo_quando_csv_nao_numera(tmp_path):
    linhas = "TIPO_B;CAR;;;2025-02-05;ata_car.pdf;presente\n"
    corpus_path = _montar_corpus(tmp_path, linhas)

    atas = coletar_atas(corpus_path)

    assert atas[0].numero_reuniao is None


def test_numero_reuniao_nulo_quando_identificador_nao_e_inteiro(tmp_path):
    linhas = "TIPO_B;CT;extra4;Extraordinaria;2025-12-03;ata_extra.pdf;presente\n"
    corpus_path = _montar_corpus(tmp_path, linhas)

    atas = coletar_atas(corpus_path)

    assert atas[0].numero_reuniao is None


def test_levanta_erro_se_pdf_nao_existe_no_disco(tmp_path):
    linhas = "TIPO_A;CCENS_DB;1;Ordinaria;2025-02-04;ata_inexistente.pdf;presente\n"
    corpus_path = _montar_corpus(tmp_path, linhas, criar_pdfs=False)

    with pytest.raises(FileNotFoundError):
        coletar_atas(corpus_path)
