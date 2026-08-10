from pathlib import Path

import pytest

from app.ingestion.extractor import (
    CENTRO_CAMPUS,
    extrair_campos,
    extrair_horario_inicio,
    extrair_local,
    extrair_metadados_organizacionais,
    extrair_modalidade,
    extrair_quorum_declarado,
    extrair_texto_bruto,
    mapear_campus,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "atas_sample"


def test_metadados_tipo_a_camara_departamental():
    meta = extrair_metadados_organizacionais("TIPO_A", "CCENS_DB")
    assert meta == {
        "centro": "CCENS", "campus": "Alegre", "tipo_orgao": "A", "departamento": "DB", "curso": None, "area_tematica": None,
    }


def test_metadados_tipo_b_conselho_do_centro():
    meta = extrair_metadados_organizacionais("TIPO_B", "CT")
    assert meta == {
        "centro": "CT", "campus": "Goiabeiras", "tipo_orgao": "B", "departamento": None, "curso": None, "area_tematica": None,
    }


def test_metadados_tipo_c_camara_local_tematica():
    meta = extrair_metadados_organizacionais("TIPO_C", "CCHN_CamaraLocal_Graduacao")
    assert meta == {
        "centro": "CCHN", "campus": "Goiabeiras", "tipo_orgao": "C", "departamento": None, "curso": None, "area_tematica": "Graduacao",
    }


def test_metadados_tipo_d_colegiado_de_curso():
    meta = extrair_metadados_organizacionais("TIPO_D", "CE_Colegiado_Pedagogia")
    assert meta == {
        "centro": "CE", "campus": "Goiabeiras", "tipo_orgao": "D", "departamento": None, "curso": "Pedagogia", "area_tematica": None,
    }


def test_metadados_centro_sem_campus_mapeado_levanta_erro():
    with pytest.raises(ValueError, match="centro sem campus mapeado"):
        extrair_metadados_organizacionais("TIPO_B", "CCJE")


def test_extrair_texto_bruto_retorna_conteudo_nao_vazio():
    caminho = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CAR" / "ata_05_02_2025.pdf"
    texto = extrair_texto_bruto(caminho)
    assert "CENTRO DE ARTES" in texto.upper()


def test_horario_formato_digito_compacto():
    assert extrair_horario_inicio("às 13h30, realizou-se a reunião") == "13:30"


def test_horario_extenso_hora_e_minutos():
    assert extrair_horario_inicio("REALIZADA EM 4 DE MAIO DE 2022, ÀS TREZE HORAS E TRINTA MINUTOS.") == "13:30"


def test_horario_extenso_hora_e_minutos_sem_palavra_horas():
    assert extrair_horario_inicio("às catorze e zero minutos, foi realizada") == "14:00"


def test_horario_extenso_so_hora():
    assert extrair_horario_inicio("REALIZADA EM QUATRO DE MAIO DE 2022, ÀS QUATORZE HORAS.") == "14:00"


def test_horario_ausente_retorna_none():
    assert extrair_horario_inicio("Ata da reunião ordinária, sem horário declarado.") is None


def test_horario_tolera_layout_com_quebra_de_linha_entre_palavras():
    texto = "às\n         \ncatorze\n         \ne\nzero\n         \nminutos,\n         \nfoi realizada"
    assert extrair_horario_inicio(texto) == "14:00"


def test_modalidade_videoconferencia():
    assert extrair_modalidade("realizada por meio da webconferência, no dia tal") == "Videoconferência"


def test_modalidade_google_meet_com_espacamento_irregular():
    texto = "foi realizada no(a)\n         \nGoogle\n         \nMeet\n         \na décima sessão"
    assert extrair_modalidade(texto) == "Videoconferência"


def test_modalidade_consulta_eletronica():
    assert extrair_modalidade("por meio de consulta enviada por e-mail no dia tal") == "Consulta eletrônica"


def test_modalidade_presencial():
    assert extrair_modalidade("realizada na sala de reuniões dos conselhos departamentais") == "Presencial"


def test_modalidade_ausente_retorna_none():
    assert extrair_modalidade("Ata da reunião ordinária, sem modalidade declarada.") is None


def test_local_extrai_link_de_videoconferencia():
    texto = "realizada por meio da webconferência, https://meet.google.com/abc-defg-hij, no dia tal"
    assert extrair_local(texto) == "https://meet.google.com/abc-defg-hij"


def test_local_extrai_sala_fisica():
    texto = "realizada na sala de reuniões dos conselhos departamentais, sob a presidência"
    assert extrair_local(texto) == "Sala De Reuniões Dos Conselhos Departamentais"


def test_quorum_declarado_true():
    assert extrair_quorum_declarado("Havendo quórum, foi iniciada a reunião") is True


def test_quorum_declarado_true_variante_numero_legal():
    assert extrair_quorum_declarado("Havendo número legal de membros presentes, a sessão foi aberta") is True


def test_quorum_declarado_false():
    assert extrair_quorum_declarado("Não havendo quórum, a reunião foi cancelada") is False


def test_quorum_ausente_retorna_none():
    assert extrair_quorum_declarado("Ata da reunião ordinária, sem menção a quórum.") is None


@pytest.mark.parametrize("centro, campus_esperado", list(CENTRO_CAMPUS.items()))
def test_mapear_campus_cobre_todos_os_centros_do_corpus(centro, campus_esperado):
    assert mapear_campus(centro) == campus_esperado


def test_mapear_campus_centro_desconhecido_levanta_erro():
    with pytest.raises(ValueError, match="centro sem campus mapeado"):
        mapear_campus("CCJE")


def test_extrair_campos_fixture_ccae():
    caminho = (
        FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CCAE"
        / "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf"
    )
    campos = extrair_campos("TIPO_B", "CCAE", caminho)

    assert campos["centro"] == "CCAE"
    assert campos["campus"] == "Alegre"
    assert campos["tipo_orgao"] == "B"
    assert campos["horario_inicio"] == "14:00"
    assert campos["modalidade"] == "Presencial"
    assert campos["quorum_declarado"] is True
    assert "reuni" in campos["local"].lower()
    assert len(campos["texto_bruto"]) > 100


def test_extrair_campos_fixture_ct_layout_espacado():
    caminho = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CT" / "10-2025.pdf"
    campos = extrair_campos("TIPO_B", "CT", caminho)

    assert campos["centro"] == "CT"
    assert campos["campus"] == "Goiabeiras"
    assert campos["horario_inicio"] == "14:00"
    assert campos["modalidade"] == "Videoconferência"
    assert campos["quorum_declarado"] is True
