import logging
import shutil
from pathlib import Path

import fitz
import pytest

from app.ingestion.extractor import (
    CENTRO_CAMPUS,
    _neutralizar_numeracao_de_margem,
    _remover_cabecalho_e_rodape_repetidos,
    TesseractAusenteError,
    extrair_campos,
    extrair_horario_inicio,
    extrair_local,
    extrair_marca_dagua_em_aprovacao,
    extrair_metadados_organizacionais,
    extrair_modalidade,
    extrair_quorum_declarado,
    extrair_texto_bruto,
    mapear_campus,
    normalizar_ligaduras,
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


def test_metadados_tipo_a_sem_departamento_retorna_none():
    meta = extrair_metadados_organizacionais("TIPO_A", "CT")
    assert meta["departamento"] is None


def test_metadados_tipo_c_area_tematica_com_multiplos_segmentos_nao_trunca():
    meta = extrair_metadados_organizacionais("TIPO_C", "CT_CamaraLocal_Ensino_Pesquisa")
    assert meta["area_tematica"] == "Ensino_Pesquisa"


def test_metadados_tipo_d_curso_com_multiplos_segmentos_nao_trunca():
    meta = extrair_metadados_organizacionais("TIPO_D", "CE_Colegiado_Engenharia_Producao")
    assert meta["curso"] == "Engenharia_Producao"


def test_extrair_texto_bruto_retorna_conteudo_nao_vazio():
    caminho = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CAR" / "ata_05_02_2025.pdf"
    texto, _offsets, _paginas_ocr = extrair_texto_bruto(caminho)
    assert "CENTRO DE ARTES" in texto.upper()


def test_extrair_texto_bruto_retorna_offsets_de_pagina():
    caminho = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CT" / "10-2025.pdf"
    texto, offsets, _paginas_ocr = extrair_texto_bruto(caminho)

    assert offsets[0] == 0
    assert len(offsets) >= 2
    assert all(offsets[i] < offsets[i + 1] for i in range(len(offsets) - 1))
    for offset in offsets:
        assert 0 <= offset <= len(texto)


def test_extrair_texto_bruto_corrige_ligadura_ti_quebrada():
    caminho = (
        FIXTURES / "TIPO_C__Camara_Local_Tematica" / "CCHN_CamaraLocal_Graduacao"
        / "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf"
    )
    texto, _offsets, _paginas_ocr = extrair_texto_bruto(caminho)
    assert "Ɵ" not in texto
    assert "participar" in texto


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


def test_horario_extenso_minuto_composto():
    texto = "REALIZADA EM 4 DE MAIO DE 2022, ÀS QUATORZE HORAS E TRINTA E CINCO MINUTOS."
    assert extrair_horario_inicio(texto) == "14:35"


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


def test_modalidade_prioriza_ultimo_indicio_quando_modalidade_e_descartada_antes():
    texto = "Diante da impossibilidade de webconferência, a reunião ocorreu presencialmente na sala de reuniões do centro."
    assert extrair_modalidade(texto) == "Presencial"


def test_local_extrai_link_de_videoconferencia():
    texto = "realizada por meio da webconferência, https://meet.google.com/abc-defg-hij, no dia tal"
    assert extrair_local(texto) == "https://meet.google.com/abc-defg-hij"


def test_local_extrai_sala_fisica():
    texto = "realizada na sala de reuniões dos conselhos departamentais, sob a presidência"
    assert extrair_local(texto) == "Sala De Reuniões Dos Conselhos Departamentais"


def test_local_remove_parenteses_de_fechamento_do_link():
    texto = "a reunião ocorreu por videoconferência (https://meet.google.com/abc-defg-hij)."
    assert extrair_local(texto) == "https://meet.google.com/abc-defg-hij"


def test_quorum_declarado_true():
    assert extrair_quorum_declarado("Havendo quórum, foi iniciada a reunião") is True


def test_quorum_declarado_true_variante_numero_legal():
    assert extrair_quorum_declarado("Havendo número legal de membros presentes, a sessão foi aberta") is True


def test_quorum_declarado_false():
    assert extrair_quorum_declarado("Não havendo quórum, a reunião foi cancelada") is False


def test_quorum_ausente_retorna_none():
    assert extrair_quorum_declarado("Ata da reunião ordinária, sem menção a quórum.") is None


def test_quorum_prioriza_ultimo_indicio_quando_falta_na_primeira_chamada_e_atinge_na_segunda():
    texto = "Não houve quórum na primeira chamada. Havendo quórum na segunda chamada, deu-se início à sessão."
    assert extrair_quorum_declarado(texto) is True


def test_em_aprovacao_true_quando_marca_dagua_no_cabecalho():
    texto = "ATA EM APROVAÇÃO\n\nATA DA 5ª SESSÃO ORDINÁRIA DO CONSELHO DEPARTAMENTAL"
    assert extrair_marca_dagua_em_aprovacao(texto) is True


def test_em_aprovacao_false_quando_ausente():
    texto = "ATA DA 5ª SESSÃO ORDINÁRIA DO CONSELHO DEPARTAMENTAL, realizada no dia tal"
    assert extrair_marca_dagua_em_aprovacao(texto) is False


def test_em_aprovacao_false_quando_mencao_fora_da_janela_de_abertura():
    # reproduz o falso-positivo real do corpus (ata_5a_reuniao_ordinaria_det_ceunes):
    # mencao incidental "da ata em aprovacao" no corpo, apos a janela de abertura
    abertura = "ATA DA 5ª SESSÃO ORDINÁRIA DO CONSELHO DEPARTAMENTAL, realizada no dia tal. "
    preenchimento = "x" * 3000
    texto = abertura + preenchimento + " Foi aprovada a pauta 3 da ata em aprovação anterior."
    assert extrair_marca_dagua_em_aprovacao(texto) is False


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
    assert "reuni" in extrair_local(campos["texto_bruto"]).lower()
    assert len(campos["texto_bruto"]) > 100


def test_extrair_campos_fixture_ct_layout_espacado():
    caminho = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CT" / "10-2025.pdf"
    campos = extrair_campos("TIPO_B", "CT", caminho)

    assert campos["centro"] == "CT"
    assert campos["campus"] == "Goiabeiras"
    assert campos["horario_inicio"] == "14:00"
    assert campos["modalidade"] == "Videoconferência"
    assert campos["quorum_declarado"] is True
    assert campos["em_aprovacao"] is True


def test_extrair_texto_bruto_loga_aviso_do_mupdf_em_vez_de_vazar_pro_stderr(caplog, monkeypatch):
    caminho_qualquer = next(FIXTURES.glob("**/*.pdf"))
    monkeypatch.setattr(
        fitz.TOOLS, "mupdf_warnings", lambda: "syntax error: unknown keyword: '0,5020'"
    )

    with caplog.at_level(logging.WARNING, logger="app.ingestion.extractor"):
        extrair_texto_bruto(caminho_qualquer)

    assert any("MuPDF" in registro.message for registro in caplog.records)


CCENS_DB = FIXTURES / "TIPO_A__Camara_Departamental" / "CCENS_DB" / "ata_da_1a_reuniao_ordinaria_-_db_ccens_04-02-2025.docx.pdf"
CAR = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CAR" / "ata_05_02_2025.pdf"
CT = FIXTURES / "TIPO_B__Conselho_Departamental_do_Centro" / "CT" / "10-2025.pdf"
CCHN_CAMARA_LOCAL = FIXTURES / "TIPO_C__Camara_Local_Tematica" / "CCHN_CamaraLocal_Graduacao" / "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf"
CCENS_DC = FIXTURES / "TIPO_A__Camara_Departamental" / "CCENS_DC" / "ata_da_01a_reuniao_de_carater_ordinario_dc_29_01_2025.docx.pdf"
CCENS_DC_2_PAGINAS = FIXTURES / "TIPO_A__Camara_Departamental" / "CCENS_DC" / "ata_da_08a_reuniao_de_carater_ordinario_dc_27_06_2025.docx.pdf"


def test_extrair_texto_bruto_remove_cabecalho_institucional_repetido_da_pagina_seguinte():
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CCENS_DB)
    pagina2 = texto[offsets[1]:]

    assert "Universidade Federal do Espírito Santo" not in pagina2
    assert pagina2.lstrip().startswith("Pós-Graduação em Agroquímica")


def test_extrair_texto_bruto_preserva_cabecalho_da_primeira_pagina():
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CCENS_DB)
    pagina1 = texto[offsets[0]:offsets[1]]

    assert "Universidade Federal do Espírito Santo" in pagina1


def test_extrair_texto_bruto_remove_cabecalho_repetido_em_multiplas_paginas():
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CCHN_CAMARA_LOCAL)
    pagina2 = texto[offsets[1]:]

    assert "CONSELHO DEPARTAMENTAL" not in pagina2
    assert pagina2.lstrip().startswith("encerrada a sessão")


def test_extrair_texto_bruto_preserva_numero_isolado_de_pagina_sem_linha_fixa_de_rodape():
    # a pagina termina so com o numero da pagina solto (ex.: "...de \n1 \n\n"), sem
    # nenhuma linha fixa antes dele repetida entre paginas -- nao ha como distinguir
    # com confianca de um numero que faca parte do proprio conteudo do item (ver
    # caso real do fixture colped/CE-D), entao esse caso fica de fora de proposito
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CCENS_DB)
    pagina1 = texto[offsets[0]:offsets[1]]

    assert pagina1.rstrip().endswith("1")


def test_extrair_texto_bruto_remove_rodape_com_timestamp_fixo_e_contador_de_pagina_variavel():
    texto, _offsets, _paginas_ocr = extrair_texto_bruto(CT)

    assert "Emissão: 11/03/2026 12:00:13" not in texto
    assert "Página 1/8" not in texto
    assert "Página 8/8" not in texto


def test_extrair_texto_bruto_nao_remove_nada_quando_paginas_nao_repetem_conteudo():
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CAR)
    pagina2 = texto[offsets[1]:]

    assert pagina2.lstrip().startswith("concessão da solicitação")


def test_extrair_texto_bruto_remove_cabecalho_mesmo_com_linha_em_branco_extra_na_primeira_pagina():
    # a 1a pagina desse documento real tem uma linha em branco a mais no topo do
    # que as paginas seguintes (" \n \nUniversidade..." vs " \nUniversidade...")
    # -- exigir que a 1a pagina bata linha a linha com as demais pra descobrir o
    # cabecalho falharia aqui; o padrao precisa ser descoberto so entre as
    # paginas 2+ quando ha pelo menos duas delas pra concordar entre si
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CCENS_DC)
    pagina2 = texto[offsets[1]:]

    assert "Universidade Federal do Espírito Santo" not in pagina2
    assert pagina2.lstrip().startswith("Campus e também sobre os cursos")


def test_extrair_texto_bruto_remove_cabecalho_com_linha_em_branco_extra_em_documento_de_2_paginas():
    # mesmo problema do teste anterior, mas no caso de fallback (documento com
    # so 2 paginas, onde a 1a obrigatoriamente entra na comparacao porque nao ha
    # nenhuma outra pagina pra descobrir o padrao sem ela)
    texto, offsets, _paginas_ocr = extrair_texto_bruto(CCENS_DC_2_PAGINAS)
    pagina2 = texto[offsets[1]:]

    assert "Universidade Federal do Espírito Santo" not in pagina2
    assert pagina2.lstrip().startswith("exoneração oficialmente")


def test_neutralizar_numeracao_de_margem_remove_linhas_que_se_repetem_na_pagina():
    texto = "PRIMEIRA LINHA\n8\nSEGUNDA LINHA\n9\nTERCEIRA LINHA"
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert len(resultado) == len(texto)
    assert "8" not in resultado
    assert "9" not in resultado
    assert "PRIMEIRA LINHA" in resultado


def test_neutralizar_numeracao_de_margem_preserva_numero_dentro_da_linha():
    texto = "1. ORDEM DO DIA: 1.1 ITEM.\n8\nCONTINUAÇÃO.\n9\nMAIS TEXTO."
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert "1. ORDEM DO DIA: 1.1 ITEM." in resultado


def test_neutralizar_numeracao_de_margem_preserva_numero_isolado_sem_repeticao_na_pagina():
    texto = "Atuação no Programa de \n1 \n\n"
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert resultado.rstrip().endswith("1")


def test_neutralizar_numeracao_de_margem_remove_numero_que_e_ultima_linha_do_texto_se_repetir_antes():
    texto = "8\nCONTEUDO DA PAGINA\n9"
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert "8" not in resultado
    assert "9" not in resultado


def test_neutralizar_numeracao_de_margem_preserva_data_com_dia_isolado_na_propria_linha():
    # layout "uma palavra por linha" real de atas CEUNES: o dia da data fica
    # sozinho na linha, sem nenhuma outra numeracao de margem na pagina pra
    # confirmar que e um contador repetido -- nao pode ser apagado
    texto = "São Mateus/ES, \n15 \nde fevereiro de 2023."
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert "15" in resultado


def test_extrair_texto_bruto_corrige_numero_de_processo_partido_por_numeracao_de_margem(tmp_path):
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text(
        (72, 72),
        "25 \nOutro trecho qualquer da ata antes do processo.\n"
        "3.3 - Processo digital nº 23068.031941/2024-\n26 \n91 – Interessado: Fulano.",
    )
    caminho = tmp_path / "margem.pdf"
    doc.save(caminho)
    doc.close()

    from app.ingestion.cleaner import RE_NUMERO_PROCESSO

    texto, _offsets, _paginas_ocr = extrair_texto_bruto(caminho)
    match = RE_NUMERO_PROCESSO.search(texto)

    assert match is not None
    assert "".join(match.group(0).split()) == "23068.031941/2024-91"


def test_remove_cabecalho_nao_quebra_quando_primeira_pagina_e_mais_curta_que_as_outras():
    # a pagina[0] entra na comparacao pra descobrir o cabecalho (mesmo nunca
    # sendo alvo do corte) -- se ela for mais curta que as demais, o indice
    # pode ultrapassar seu numero de linhas antes das outras paginas divergirem
    paginas = _remover_cabecalho_e_rodape_repetidos(
        ["CABECALHO\nFIXO", "CABECALHO\nFIXO\nCORPO1", "CABECALHO\nFIXO\nCORPO2"]
    )

    assert paginas == ["CABECALHO\nFIXO", "CORPO1", "CORPO2"]


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Justiﬁcou", "Justificou"),
        ("ﬂuentes", "fluentes"),
        ("Schiﬄer", "Schiffler"),
        ("Vitória", "Vitória"),
        ("caça", "caça"),
        ("İsicos", "físicos"),
        ("Oİcio", "Ofício"),
        ("noơcias", "notícias"),
        ("Estaơstica", "Estatística"),
        ("SoŌware", "Software"),
        ("parƟcipar", "participar"),
    ],
)
def test_normalizar_ligaduras_corrige_casos_do_corpus(entrada, esperado):
    assert normalizar_ligaduras(entrada) == esperado


def test_normalizar_ligaduras_preserva_glifo_isolado():
    assert normalizar_ligaduras("letra İ isolada") == "letra İ isolada"


def test_normalizar_ligaduras_nao_altera_texto_comum():
    texto = "Aprovado por unanimidade.\n  Item 2: ofício nº 3/2025"
    assert normalizar_ligaduras(texto) == texto


FIXTURES_OCR = Path(__file__).parent.parent / "fixtures" / "ocr"
SEM_TESSERACT = shutil.which("tesseract") is None


@pytest.mark.skipif(SEM_TESSERACT, reason="tesseract nao instalado")
def test_extrair_texto_bruto_usa_ocr_em_pagina_escaneada():
    texto, offsets, paginas_ocr = extrair_texto_bruto(FIXTURES_OCR / "dcab_pagina_escaneada.pdf")

    assert paginas_ocr == [1]
    assert offsets == [0]
    assert "INFORME" in texto
    assert "Departamental" in texto


@pytest.mark.skipif(SEM_TESSERACT, reason="tesseract nao instalado")
def test_extrair_texto_bruto_usa_ocr_em_texto_vetorizado():
    texto, _offsets, paginas_ocr = extrair_texto_bruto(FIXTURES_OCR / "ceunes_texto_vetorizado.pdf")

    assert paginas_ocr == [1]
    assert "CONSELHO" in texto
    assert "Mateus" in texto


def test_extrair_texto_bruto_nao_chama_ocr_em_pdf_com_texto(monkeypatch):
    def _ocr_proibido(*args, **kwargs):
        raise AssertionError("OCR chamado em pagina com texto nativo")

    monkeypatch.setattr(fitz.Page, "get_textpage_ocr", _ocr_proibido)

    _texto, _offsets, paginas_ocr = extrair_texto_bruto(CAR)

    assert paginas_ocr == []


def test_extrair_texto_bruto_sem_tesseract_levanta_erro_orientando_instalacao(monkeypatch):
    def _sem_tesseract(*args, **kwargs):
        raise RuntimeError("No tessdata specified and Tesseract is not installed")

    monkeypatch.setattr(fitz.Page, "get_textpage_ocr", _sem_tesseract)

    with pytest.raises(TesseractAusenteError, match="brew install tesseract"):
        extrair_texto_bruto(FIXTURES_OCR / "dcab_pagina_escaneada.pdf")


def test_extrair_campos_expoe_paginas_ocr():
    campos = extrair_campos("TIPO_B", "CAR", CAR)
    assert campos["paginas_ocr"] == []
