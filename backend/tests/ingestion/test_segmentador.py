from datetime import date
from pathlib import Path

import pytest

from app.ingestion.pipeline import executar_pipeline
from app.ingestion.segmentador import (
    SECAO_APROVACAO_ATA,
    SECAO_COMUNICACOES,
    SECAO_EXCLUSAO_DE_PAUTA,
    SECAO_EXPEDIENTE,
    SECAO_INFORMES,
    SECAO_ORDEM_DO_DIA,
    SECAO_PALAVRA_LIVRE,
    SECAO_PAUTA,
    SECAO_PROCESSOS_PROJETOS,
    SOBREPOSICAO_FRAGMENTO,
    TAMANHO_MAX_FRAGMENTO,
    _normalizar_com_mapa,
    detectar_itens_familia_pontilhada,
    detectar_itens_car,
    detectar_itens_cce,
    detectar_itens_ce_d,
    detectar_itens_ct,
    detectar_itens_cefd,
    dividir_fragmentos,
    gerar_item_id_canonico,
    mapear_pagina,
    segmentar_texto,
    segmentar_e_persistir,
)
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta

FIXTURES = Path(__file__).parent.parent / "fixtures" / "atas_sample"
SECRET_KEY_SEGMENTADOR = b"chave-de-teste-nao-usar-em-producao"


def test_normalizar_com_mapa_colapsa_espacos_multiplos():
    normalizado, mapa = _normalizar_com_mapa("A   B")
    assert normalizado == "A B"
    assert len(mapa) == len(normalizado)


def test_normalizar_com_mapa_colapsa_quebras_de_linha():
    normalizado, mapa = _normalizar_com_mapa("A\n\n  B\nC")
    assert normalizado == "A B C"


def test_normalizar_com_mapa_preserva_offset_correto():
    original = "AB  CD"
    normalizado, mapa = _normalizar_com_mapa(original)
    assert normalizado == "AB CD"
    indice_c = normalizado.index("C")
    assert original[mapa[indice_c]] == "C"


def test_normalizar_com_mapa_string_vazia():
    normalizado, mapa = _normalizar_com_mapa("")
    assert normalizado == ""
    assert mapa == []


def test_familia_pontilhada_secao_unica_tipo_a():
    texto = (
        "HAVENDO QUÓRUM, FOI INICIADA A REUNIÃO. 1. ORDEM DO DIA. "
        "1.1 APRECIAÇÃO DO CALENDÁRIO. TEXTO DO ITEM UM PONTO UM. "
        "1.2 - OUTRO ITEM. TEXTO DO ITEM UM PONTO DOIS."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_ORDEM_DO_DIA, "1.1"),
        (SECAO_ORDEM_DO_DIA, "1.2"),
    ]


def test_familia_pontilhada_multiplas_secoes():
    texto = (
        "1. APROVAÇÃO DA ATA: 1.1 ATA ANTERIOR APROVADA. "
        "2. EXPEDIENTE: 2.1 PROCESSO INCLUÍDO. "
        "3. COMUNICAÇÃO: 3.1 COMUNICADO UM. 3.2 COMUNICADO DOIS."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_APROVACAO_ATA, "1.1"),
        (SECAO_EXPEDIENTE, "2.1"),
        (SECAO_COMUNICACOES, "3.1"),
        (SECAO_COMUNICACOES, "3.2"),
    ]


def test_familia_pontilhada_secao_sem_itens_e_pulada():
    texto = "1. PAUTA: 1.1 ÚNICO ITEM. 2. PALAVRA LIVRE: NÃO HOUVE SOLICITAÇÃO DE REGISTRO."
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1.1")]


def test_familia_pontilhada_aceita_pauta_no_plural():
    texto = "1. EXPEDIENTE: NÃO HOUVE. 3. PAUTAS: 3.1 – DOCUMENTO AVULSO Nº 123."
    itens = detectar_itens_familia_pontilhada(texto)
    assert (SECAO_PAUTA, "3.1") in [(i.secao, i.numero_item) for i in itens]


def test_familia_pontilhada_ignora_numero_de_token_de_anonimizacao():
    texto = "REUNIÃO SOB A PRESIDÊNCIA DA PROFESSORA PESSOA_12752. INFORMES: PAUTA: 1) ITEM."
    itens = detectar_itens_familia_pontilhada(texto)
    assert itens == []


def test_familia_pontilhada_ignora_numero_citado_entre_aspas():
    texto = (
        '1. APRECIAÇÃO DE ATA: 1.1. A PROFESSORA SUGERIU A REVISÃO DO TÓPICO '
        '“1.4” DA ATA ANTERIOR. 2. EXPEDIENTE: 2.1 ITEM SEGUINTE.'
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_APROVACAO_ATA, "1.1"),
        (SECAO_EXPEDIENTE, "2.1"),
    ]


def test_familia_pontilhada_cabecalho_de_secao_sem_acento():
    texto = "1. APROVACAO DA ATA: 1.1 ATA ANTERIOR APROVADA."
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_APROVACAO_ATA, "1.1")]


def test_familia_pontilhada_cabecalho_de_secao_combinacao_nao_prevista_no_alias():
    texto = "1. APRECIAÇÃO DA ATA: 1.1 ATA ANTERIOR APROVADA."
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_APROVACAO_ATA, "1.1")]


def test_familia_pontilhada_aceita_secao_sem_pontuacao_antes_do_subitem():
    texto = (
        "1. EXPEDIENTE NÃO HOUVE. "
        "2. ORDEM DO DIA 2.1 APROVAÇÃO DO CALENDÁRIO DE REUNIÕES."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_ORDEM_DO_DIA, "2.1"),
    ]


def test_familia_pontilhada_secao_sem_pontuacao_e_sem_subitem_fica_vazia():
    texto = "1. EXPEDIENTE NÃO HOUVE."
    assert detectar_itens_familia_pontilhada(texto) == []


def test_familia_pontilhada_nao_trunca_secao_em_numero_coincidente_no_meio_da_frase():
    texto = (
        "1. EXPEDIENTE: 1.1 LEITURA DA RESOLUCAO 43. COMUNICADOS FORAM FEITOS "
        "PELA DIRECAO. 1.2 OUTRO ITEM."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_EXPEDIENTE, "1.1"),
        (SECAO_EXPEDIENTE, "1.2"),
    ]


def test_familia_pontilhada_reclassifica_exclusao_de_pauta_do_primeiro_item():
    texto = (
        "2. EXPEDIENTE: EXCLUSÃO DE PAUTA: 2.1 ITEM RETIRADO. "
        "2.2 OUTRO ITEM, SEM RELAÇÃO COM EXCLUSÃO."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert itens[0].secao == SECAO_EXCLUSAO_DE_PAUTA
    assert itens[1].secao == SECAO_EXPEDIENTE


def test_familia_pontilhada_primeiro_item_nao_carrega_preambulo_da_secao():
    texto = (
        "2. EXPEDIENTE: A Presidente solicitou a inclusão de pontos extras na "
        "pauta, a saber: 2.1 Processo digital tal. 2.2 Outro item qualquer."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert itens[0].texto.startswith("2.1")
    assert "Presidente solicitou" not in itens[0].texto


def test_familia_pontilhada_aprovacao_de_ata_preserva_decisao_antes_do_marcador():
    texto = (
        "1. APROVAÇÃO DE ATA: Foi apreciada e aprovada, por unanimidade: "
        "1.1 Ata da Sessão Ordinária, realizada em 17 de dezembro de 2024."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert itens[0].texto.startswith("Foi apreciada e aprovada, por unanimidade")


def test_familia_pontilhada_reclassificacao_nao_se_aplica_a_secao_sem_subtitulo():
    texto = "2. EXPEDIENTE: 2.1 ITEM NORMAL, SEM SUBTÍTULO DE EXCLUSÃO."
    itens = detectar_itens_familia_pontilhada(texto)
    assert itens[0].secao == SECAO_EXPEDIENTE


def test_detectar_itens_ct():
    texto = (
        "HAVENDO NÚMERO LEGAL, DECLAROU ABERTA A SESSÃO. INFORME 1: TEXTO DO INFORME UM. "
        "INFORME 2: TEXTO DO INFORME DOIS. PAUTA 1: PRIMEIRO ITEM DE PAUTA. "
        "PAUTA 2: SEGUNDO ITEM DE PAUTA."
    )
    itens = detectar_itens_ct(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_INFORMES, "1"),
        (SECAO_INFORMES, "2"),
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_detectar_itens_car():
    texto = "INFORMES: PAUTA: 1) PRIMEIRO ITEM. 2) SEGUNDO ITEM. 04) TERCEIRO ITEM COM PADDING."
    itens = detectar_itens_car(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
        (SECAO_PAUTA, "04"),
    ]


def test_detectar_itens_car_sem_pauta_retorna_vazio():
    assert detectar_itens_car("TEXTO SEM A PALAVRA PAUTA.") == []


def test_detectar_itens_car_ignora_numero_citado_entre_aspas():
    texto = 'PAUTA: 1) PRIMEIRO ITEM QUE MENCIONA O ITEM "3)" DA PAUTA ANTERIOR. 2) SEGUNDO ITEM.'
    itens = detectar_itens_car(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_detectar_itens_ct_ignora_numero_citado_entre_aspas():
    texto = 'PAUTA 1: PRIMEIRO ITEM QUE MENCIONA "PAUTA 3:" DE OUTRA ATA. PAUTA 2: SEGUNDO ITEM.'
    itens = detectar_itens_ct(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_detectar_itens_cefd_ignora_numero_citado_entre_aspas():
    texto = 'EM PAUTA: [1] PRIMEIRO ITEM QUE MENCIONA O ITEM "[3]" DE OUTRA ATA. [2] SEGUNDO ITEM.'
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_detectar_itens_cefd():
    texto = (
        "EM PAUTA: LEITURA DA ATA APROVADA POR UNANIMIDADE. "
        "COMUNICAÇÕES: O DIRETOR FEZ COMUNICADOS: [1] PRIMEIRO COMUNICADO. [2] SEGUNDO COMUNICADO. "
        "PROCESSOS/PROJETOS: [1] HOMOLOGAÇÃO DE AFASTAMENTO. [2] OUTRO PROCESSO. "
        "PALAVRA LIVRE: SEM REGISTRO."
    )
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_COMUNICACOES, "1"),
        (SECAO_COMUNICACOES, "2"),
        (SECAO_PROCESSOS_PROJETOS, "1"),
        (SECAO_PROCESSOS_PROJETOS, "2"),
        (SECAO_PALAVRA_LIVRE, "1"),
    ]


def test_detectar_itens_cefd_secao_sem_marcador_vira_item_unico():
    texto = "EM PAUTA: SEM ITENS NUMERADOS. PALAVRA LIVRE: NENHUM REGISTRO."
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item, i.texto) for i in itens] == [
        (SECAO_PAUTA, "1", "SEM ITENS NUMERADOS."),
        (SECAO_PALAVRA_LIVRE, "1", "NENHUM REGISTRO."),
    ]


@pytest.mark.parametrize("corpo", [
    "Não houve…................………………………………………………",
    "Não houve…………….. ",
    "NÃO HOUVE.",
    "nao  houve",
])
def test_cefd_secao_so_com_nao_houve_nao_vira_item(corpo):
    itens = detectar_itens_cefd(f"COMUNICAÇÕES: A reitoria comunicou o calendário. PALAVRA LIVRE: {corpo}")
    assert [(i.secao, i.texto) for i in itens] == [(SECAO_COMUNICACOES, "A reitoria comunicou o calendário.")]


def test_cefd_ultima_secao_so_com_nao_houve_antes_do_encerramento_nao_vira_item():
    texto = (
        "COMUNICAÇÕES: A reitoria comunicou o calendário. PALAVRA LIVRE: Não \nhouve……………….\n.\n"
        "Nada mais havendo a tratar, a reunião foi encerrada. Vitória, 30 de agosto de 2023."
    )
    itens, _ = segmentar_texto("B", "CEFD", texto)
    assert [(i.secao, i.texto) for i in itens] == [(SECAO_COMUNICACOES, "A reitoria comunicou o calendário.")]


def test_cefd_ultima_secao_com_conteudo_depois_do_nao_houve_vira_item():
    texto = (
        "PALAVRA LIVRE: Não houve…… O acadêmico PESSOA_0002 questionou a reforma.\n"
        "Nada mais havendo a tratar, a reunião foi encerrada."
    )
    itens, _ = segmentar_texto("B", "CEFD", texto)
    assert [(i.secao, i.texto) for i in itens] == [
        (SECAO_PALAVRA_LIVRE, "Não houve…… O acadêmico PESSOA_0002 questionou a reforma.")
    ]


@pytest.mark.parametrize("corpo", [
    "Não houve, mas o professor PESSOA_0001 comunicou a reforma da cantina.",
    "Não houve quórum para deliberar.",
    "Não houve…….. O acadêmico PESSOA_0002 questionou a reforma.",
])
def test_cefd_secao_que_continua_depois_do_nao_houve_vira_item(corpo):
    itens = detectar_itens_cefd(f"PALAVRA LIVRE: {corpo}")
    assert [(i.secao, i.texto) for i in itens] == [(SECAO_PALAVRA_LIVRE, corpo)]


def test_cefd_aceita_ponto_final_em_vez_de_dois_pontos_no_cabecalho():
    texto = "PROCESSOS/PROJETOS. [1] SOLICITAÇÃO DE AFASTAMENTO PARA DOUTORADO."
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PROCESSOS_PROJETOS, "1"),
    ]


def test_cefd_secao_ignora_narrativa_com_termos_de_secao_em_minuscula():
    texto = (
        "PROCESSOS/PROJETOS: [1] PRIMEIRO PROCESSO. O relator informou que o "
        "assunto foi colocado em pauta. O relator apresentou o parecer final "
        "apos fazer comunicações. Ficou definido que sera tratado em palavra "
        "livre. [2] SEGUNDO PROCESSO."
    )
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PROCESSOS_PROJETOS, "1"),
        (SECAO_PROCESSOS_PROJETOS, "2"),
    ]
    assert "parecer final" in itens[0].texto


def test_detectar_itens_cce_ponto_numerado_com_ponto_final():
    texto = "DECLAROU ABERTA A SESSÃO. Ponto 01. Comunicações: TEXTO. Ponto 02. TEXTO DOIS."
    itens = detectar_itens_cce(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "01"),
        (SECAO_PAUTA, "02"),
    ]


def test_detectar_itens_cce_ordem_invertida_maiuscula_de_ata_antiga():
    texto = "DECLAROU ABERTA A SESSÃO. . PONTO 1 – COMUNICAÇÕES – TEXTO. PONTO 2 – TEXTO DOIS."
    itens = detectar_itens_cce(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_detectar_itens_cce_ordem_invertida_com_numeral_ordinal():
    texto = "DECLAROU ABERTA A SESSÃO. . 1º. Ponto – Mudança de composição de banca."
    itens = detectar_itens_cce(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_detectar_itens_cce_ponto_unico_vira_item_numero_1():
    texto = "DECLAROU ABERTA A SESSÃO. Ponto único – Pedido de Abertura de Concurso Público."
    itens = detectar_itens_cce(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_detectar_itens_cce_sem_estrutura_retorna_vazio():
    assert detectar_itens_cce("ATA SEM NENHUM PONTO DE PAUTA NUMERADO NO TEXTO.") == []


def test_cce_aceita_subitem_decimal_ponto_n_m():
    texto = (
        "Ponto 8 – Homologações: 8.1 – Proc. Nº PROCESSO_3479 – Homologação "
        "da Eleição de Chefe e Subchefe do Departamento de Física. . 8.2 – "
        "Concurso Público para Professor Adjunto para a área de Química – "
        "Retirado de pauta. . Ponto 8.3 – Prot. Nº PROCESSO_3478 - Alteração "
        "da Composição da Banca para Concurso de professor Visitante "
        "Estrangeiro. . Ponto 8.4 – Homologação do Termo de Cooperação "
        "Petrobrás x UFES."
    )
    itens = detectar_itens_cce(texto)
    assert [i.numero_item for i in itens] == ["8", "8.3", "8.4"]


def test_cce_ponto_repetido_sem_decimal_nao_captura_subitem_solto():
    texto = (
        "Ponto 3 – Afastamentos: 3.1 – Processo Nº PROCESSO_3385 – texto "
        "um. 3.2 – Processo Nº PROCESSO_3384 – texto dois. . Ponto 3 – "
        "Afastamento: 3.6 – Processo Nº PROCESSO_3380 – texto seis."
    )
    itens = detectar_itens_cce(texto)
    assert [i.numero_item for i in itens] == ["3", "3"]


def test_ce_d_informes_com_numeracao_de_nivel_unico():
    texto = (
        "HAVENDO QUÓRUM LEGAL A COORDENADORA INICIOU A REUNIÃO. "
        "INFORMES: 1. OFÍCIO CIRCULAR Nº 6/2021 SOBRE ENSINO HÍBRIDO. "
        "2. FÉRIAS DA COORDENADORA."
    )
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_INFORMES, "1"),
        (SECAO_INFORMES, "2"),
    ]


def test_ce_d_pauta_com_numeracao_de_nivel_unico():
    texto = (
        "PAUTA. 1. APRECIAÇÃO DA ATA DA DÉCIMA REUNIÃO ORDINÁRIA. "
        "2. HOMOLOGAÇÃO DO AD REFERENDUM."
    )
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_ce_d_dispatch_via_segmentar_texto():
    texto = "INFORMES: 1. TEXTO DO INFORME UM."
    itens, _ = segmentar_texto("D", "CE", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_INFORMES, "1")]


def test_ce_d_nao_confunde_notacao_de_semestre_com_numero_de_item():
    texto = (
        "INFORMES: 1. OFÍCIO CIRCULAR Nº 6/2021 SOBRE OFERTA NO SEMESTRE "
        "LETIVO 2021/2. A PROFESSORA INFORMOU QUE NÃO OFERTARÁ DISCIPLINAS. "
        "2. FÉRIAS DA COORDENADORA."
    )
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_INFORMES, "1"),
        (SECAO_INFORMES, "2"),
    ]


def test_ce_d_item_pode_comecar_com_numero_ordinal():
    texto = "INFORMES: 1. PRIMEIRO INFORME SOBRE O EVENTO. 2. 5ª CONFERÊNCIA MUNICIPAL DE EDUCAÇÃO."
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_INFORMES, "1"),
        (SECAO_INFORMES, "2"),
    ]


def test_ce_d_tenta_familia_pontilhada_primeiro_e_e_robusto_a_secao_extra():
    texto = (
        "1. APRECIAÇÃO DE ATA: 1.1. Ata da Segunda Reunião Ordinária. "
        "2. EXPEDIENTE: 2.1. Exclusão de ponto de pauta. "
        "3. INFORMES: 3.1. Situação referente ao atendimento. "
        "4. PAUTA: 4.1. Apreciação de solicitação. "
        "5. PALAVRA LIVRE: 5.1. Primeiro ponto de palavra livre. "
        "5.2. Segundo ponto de palavra livre."
    )
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_APROVACAO_ATA, "1.1"),
        (SECAO_EXPEDIENTE, "2.1"),
        (SECAO_INFORMES, "3.1"),
        (SECAO_PAUTA, "4.1"),
        (SECAO_PALAVRA_LIVRE, "5.1"),
        (SECAO_PALAVRA_LIVRE, "5.2"),
    ]


def test_ce_d_secao_ignora_narrativa_com_a_palavra_pauta_em_minuscula():
    texto = (
        "PAUTA. 1. Primeiro item da pauta, retirado de pauta. "
        "2. Segundo item, com sucesso. Retirado de Pauta. Nada mais a tratar."
    )
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]
    assert "Nada mais a tratar" in itens[1].texto


def test_ce_d_item_sem_espaco_apos_o_ponto():
    texto = "PAUTA. 1. PRIMEIRO ITEM. 2.Segundo item sem espaço após o ponto."
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_ce_d_item_sem_espaco_nao_confunde_numeracao_de_dois_niveis():
    texto = "PAUTA. 4.1 Aprovação de item de nível dois. 4.1. Aprovação de item de nível dois de novo."
    itens = detectar_itens_ce_d(texto)
    assert itens == []


def test_segmentar_texto_cce_via_config():
    texto = "DECLAROU ABERTA A SESSÃO. Ponto 01. PRIMEIRO ITEM."
    itens, _ = segmentar_texto("B", "CCE", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "01")]


def test_segmentar_texto_tipo_a():
    texto = "1. ORDEM DO DIA. 1.1 ITEM ÚNICO."
    itens, _ = segmentar_texto("A", "CCENS", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_ORDEM_DO_DIA, "1.1")]


def test_segmentar_texto_ct_via_config():
    texto = "PAUTA 1: PRIMEIRO ITEM."
    itens, _ = segmentar_texto("B", "CT", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_segmentar_texto_ceunes_b_via_config():
    texto = "PAUTA 1: PRIMEIRO ITEM."
    itens, _ = segmentar_texto("B", "CEUNES", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_ceunes_tipo_a_usa_mesmo_formato_informe_pauta_do_tipo_b():
    texto = (
        "HAVENDO NÚMERO LEGAL DE MEMBROS, DECLAROU ABERTA A SESSÃO. "
        "INFORME 1: O chefe do departamento informou sobre o edital de concurso. "
        "INFORME 2: Foi comunicada a data da próxima reunião."
    )
    itens, _ = segmentar_texto("A", "CEUNES", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_INFORMES, "1"),
        (SECAO_INFORMES, "2"),
    ]


def test_segmentar_texto_car_via_config():
    texto = "INFORMES: PAUTA: 1) PRIMEIRO ITEM."
    itens, _ = segmentar_texto("B", "CAR", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_segmentar_texto_cefd_via_config():
    texto = "PROCESSOS/PROJETOS: [1] PRIMEIRO PROCESSO."
    itens, _ = segmentar_texto("B", "CEFD", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PROCESSOS_PROJETOS, "1")]


def test_segmentar_texto_variant_desconhecido_levanta_erro():
    with pytest.raises(ValueError, match="variante sem detector mapeado"):
        segmentar_texto("B", "CCJE", "QUALQUER TEXTO")


def test_segmentar_texto_tipo_d_neutraliza_margem_antes_de_segmentar():
    texto = "1. ORDEM DO DIA:\n8\n1.1 ITEM COM NUMERO DE MARGEM NO MEIO."
    itens, _ = segmentar_texto("D", "CE", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_ORDEM_DO_DIA, "1.1")]


def test_dividir_fragmentos_texto_curto_retorna_fragmento_unico():
    texto = "texto curto"
    assert dividir_fragmentos(texto) == [texto]


def test_dividir_fragmentos_texto_longo_divide_com_sobreposicao():
    texto = "x" * 7000
    fragmentos = dividir_fragmentos(texto)

    assert len(fragmentos) > 1
    assert all(len(f) <= TAMANHO_MAX_FRAGMENTO for f in fragmentos)
    reconstruido = fragmentos[0]
    for f in fragmentos[1:]:
        reconstruido += f[SOBREPOSICAO_FRAGMENTO:]
    assert reconstruido == texto


def test_dividir_fragmentos_texto_no_limite_exato_retorna_fragmento_unico():
    texto = "x" * TAMANHO_MAX_FRAGMENTO
    assert dividir_fragmentos(texto) == [texto]


def test_mapear_pagina_primeira_pagina():
    assert mapear_pagina(0, [0, 1500, 3200]) == 1


def test_mapear_pagina_segunda_pagina():
    assert mapear_pagina(1600, [0, 1500, 3200]) == 2


def test_mapear_pagina_terceira_pagina():
    assert mapear_pagina(3500, [0, 1500, 3200]) == 3


def test_mapear_pagina_sem_offsets_retorna_none():
    assert mapear_pagina(100, None) is None
    assert mapear_pagina(100, []) is None


def test_gerar_item_id_canonico_sem_fragmento():
    assert gerar_item_id_canonico(233, "PAUTA", "2.1", 0, 0) == "233_PAUTA_2.1"


def test_gerar_item_id_canonico_com_fragmento():
    assert gerar_item_id_canonico(233, "PAUTA", "2.1", 0, 2) == "233_PAUTA_2.1_F2"


def test_gerar_item_id_canonico_remove_acento_e_barra_da_secao():
    assert gerar_item_id_canonico(1, "PROCESSOS/PROJETOS", "1", 0, 0) == "1_PROCESSOS_PROJETOS_1"
    assert gerar_item_id_canonico(1, "EXCLUSÃO DE PAUTA", "2.1", 0, 0) == "1_EXCLUSAO_DE_PAUTA_2.1"


def test_gerar_item_id_canonico_com_ocorrencia_duplicada():
    assert gerar_item_id_canonico(456, "COMUNICACOES", "1.01", 1, 0) == "456_COMUNICACOES_1.01_D1"


def test_gerar_item_id_canonico_com_ocorrencia_e_fragmento():
    assert (
        gerar_item_id_canonico(456, "COMUNICACOES", "1.01", 1, 2) == "456_COMUNICACOES_1.01_D1_F2"
    )


def _criar_documento(sessao, **overrides) -> Documento:
    base = dict(
        nome_arquivo="teste.pdf", url_origem="http://exemplo", centro="CCENS",
        campus="Alegre", tipo_orgao="A", orgao="CCENS_DB", data_reuniao=date(2025, 1, 1),
        texto_limpo="1. ORDEM DO DIA. 1.1 PRIMEIRO ITEM. 1.2 SEGUNDO ITEM.",
        paginas_offsets=[0],
    )
    base.update(overrides)
    documento = Documento(**base)
    sessao.add(documento)
    sessao.flush()
    return documento


def test_segmentar_e_persistir_cria_itens(db_session):
    documento = _criar_documento(db_session)
    itens = segmentar_e_persistir(documento, db_session)

    assert len(itens) == 2
    assert {i.numero_item for i in itens} == {"1.1", "1.2"}
    assert all(i.documento_id == documento.id_documento for i in itens)
    assert all(i.pagina_inicio == 1 for i in itens)
    assert db_session.query(ItemPauta).filter_by(documento_id=documento.id_documento).count() == 2


def test_segmentar_e_persistir_e_idempotente(db_session):
    documento = _criar_documento(db_session)
    segmentar_e_persistir(documento, db_session)
    itens_segunda_vez = segmentar_e_persistir(documento, db_session)

    assert len(itens_segunda_vez) == 2
    assert db_session.query(ItemPauta).filter_by(documento_id=documento.id_documento).count() == 2


def test_segmentar_e_persistir_aplica_overflow_split(db_session):
    texto_longo = "1. ORDEM DO DIA. 1.1 " + ("x" * 7000)
    documento = _criar_documento(db_session, texto_limpo=texto_longo, nome_arquivo="longo.pdf")
    itens = segmentar_e_persistir(documento, db_session)

    assert len(itens) > 1
    assert {i.fragmento_indice for i in itens} == set(range(len(itens)))
    assert {i.item_id_canonico for i in itens} == {
        gerar_item_id_canonico(documento.id_documento, "ORDEM DO DIA", "1.1", 0, i.fragmento_indice)
        for i in itens
    }


def test_segmentar_e_persistir_desambigua_numero_duplicado_dentro_do_documento(db_session):
    texto = "1. COMUNICAÇÕES: 1.1 PRIMEIRO ASSUNTO. 1.1 SEGUNDO ASSUNTO, NUMERO REPETIDO NA FONTE."
    documento = _criar_documento(db_session, texto_limpo=texto)
    itens = segmentar_e_persistir(documento, db_session)

    assert len(itens) == 2
    assert {i.ocorrencia_indice for i in itens} == {0, 1}
    assert {i.item_id_canonico for i in itens} == {
        f"{documento.id_documento}_COMUNICACOES_1.1",
        f"{documento.id_documento}_COMUNICACOES_1.1_D1",
    }


def test_segmentar_as_6_fixtures_bate_com_contagem_manual(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY_SEGMENTADOR, db_session)
    contagem_esperada = {
        "ata_da_1a_reuniao_ordinaria_-_db_ccens_04-02-2025.docx.pdf": 4,
        "10-2025.pdf": 9,
        "ata_05_02_2025.pdf": 7,
        "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf": 6,
        "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf": 6,
        "ata_da_3a_reuniao_ordinaria_colped.pdf": 7,
    }

    for documento in documentos:
        itens = segmentar_e_persistir(documento, db_session)
        assert len(itens) == contagem_esperada[documento.nome_arquivo], (
            f"{documento.nome_arquivo}: esperado {contagem_esperada[documento.nome_arquivo]}, "
            f"obtido {len(itens)}"
        )


def test_segmentar_fixture_ccae_reclassifica_secoes_corretamente(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY_SEGMENTADOR, db_session)
    ccae = next(
        d for d in documentos
        if d.nome_arquivo == "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf"
    )
    itens = segmentar_e_persistir(ccae, db_session)
    secoes = {i.secao for i in itens}
    assert secoes == {SECAO_APROVACAO_ATA, SECAO_EXPEDIENTE, SECAO_ORDEM_DO_DIA, SECAO_COMUNICACOES}


def test_segmentar_fixture_camara_local_reclassifica_exclusao_de_pauta(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY_SEGMENTADOR, db_session)
    camara_local = next(
        d for d in documentos
        if d.nome_arquivo == "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf"
    )
    itens = segmentar_e_persistir(camara_local, db_session)
    exclusao = [i for i in itens if i.secao == SECAO_EXCLUSAO_DE_PAUTA]
    assert len(exclusao) == 1
    assert exclusao[0].numero_item == "2.1"


def test_segmentar_fixture_ct_paginas_preenchidas(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY_SEGMENTADOR, db_session)
    ct = next(d for d in documentos if d.nome_arquivo == "10-2025.pdf")
    itens = segmentar_e_persistir(ct, db_session)

    assert all(i.pagina_inicio is not None for i in itens)
    paginas = {i.pagina_inicio for i in itens}
    assert len(paginas) > 1
    assert min(paginas) == 1


def test_segmentar_documento_sem_paginas_offsets_deixa_pagina_nula(db_session):
    documento = _criar_documento(db_session, paginas_offsets=None, nome_arquivo="sem_paginas.pdf")
    itens = segmentar_e_persistir(documento, db_session)
    assert all(i.pagina_inicio is None and i.pagina_fim is None for i in itens)


def test_segmentar_texto_encerra_ultimo_item_na_formula_de_encerramento():
    texto = (
        "PAUTA 1: Diagnóstico do ensino de graduação no Centro de Educação – ano 2020. "
        "Retirado de pauta. Nada mais havendo a tratar, eu, PESSOA_164382, Secretária do "
        "Colegiado, lavrei a presente Ata. PROTOCOLO DE ASSINATURA SIAPE_0407 "
        "https://api.lepisma.ufes.br/arquivos-assinados/1"
    )
    itens, _ = segmentar_texto("B", "CT", texto)
    assert len(itens) == 1
    assert itens[0].texto.endswith("Retirado de pauta.")
    assert "lavrei" not in itens[0].texto


def test_segmentar_texto_mantem_itens_apos_o_ultimo_encerramento():
    texto = (
        "PAUTA 1: Primeiro assunto. Nada mais havendo a tratar, lavrei a presente ata. "
        "PAUTA 8: Alteração no PPC do curso. Aprovado por unanimidade."
    )
    itens, _ = segmentar_texto("B", "CT", texto)
    assert [i.numero_item for i in itens] == ["1", "8"]
    assert itens[0].texto == "PAUTA 1: Primeiro assunto."


def test_segmentar_texto_mantem_itens_de_atas_concatenadas():
    texto = (
        "PAUTA 1: Assunto da primeira ata. Nada mais havendo a tratar, lavrei a presente ata. "
        "Assinaturas da primeira. "
        "PAUTA 1: Assunto da segunda ata. Nada mais havendo a tratar, lavrei a presente ata. "
        "Assinaturas da segunda."
    )
    itens, _ = segmentar_texto("B", "CT", texto)
    assert [i.texto for i in itens] == [
        "PAUTA 1: Assunto da primeira ata.",
        "PAUTA 1: Assunto da segunda ata.",
    ]


def test_segmentar_texto_nao_reconhece_nada_mais_a_tratar_sem_havendo():
    texto = "PAUTA 1: Assunto. Nada mais a tratar. Fim."
    itens, _ = segmentar_texto("B", "CT", texto)
    assert "Nada mais a tratar" in itens[0].texto


def test_cefd_secao_sem_marcador_vira_um_item():
    texto = (
        "EM PAUTA: Leitura das atas da reunião ordinária, aprovadas por unanimidade."
        "COMUNICAÇÕES: A Professora PESSOA_164045 comunicou que foi enviado um questionário."
    )
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_COMUNICACOES, "1"),
    ]
    assert itens[0].texto.startswith("Leitura das atas")
    assert itens[0].texto.endswith("unanimidade.")


def test_cefd_secao_vazia_nao_gera_item():
    itens = detectar_itens_cefd("EM PAUTA: [1] Primeiro. PALAVRA LIVRE:   ")
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_detectar_itens_car_aceita_processo_em_minuscula_e_ignora_enumeracao_interna():
    texto = (
        "PAUTA: 12) processo digital nº PROCESSO_1565, Professora solicitando autorização. "
        "02) proc. digital n PROCESSO_31008. Ata do Departamento. "
        "03) Processo digital n° PROCESSO_31054, Coordenação do Curso. "
        "1) atende aos requisitos legais; 2) descreve adequadamente as atividades; "
        "2), na condição de professor permanente do PósCom. 6) / Desenho (Cód. Cnpq). "
        "17) Doc. Avulso n. 028498/25-52."
    )
    itens = detectar_itens_car(texto)
    assert [i.numero_item for i in itens] == ["12", "02", "03", "17"]


def test_detectar_itens_car_aceita_marcador_com_hifen():
    texto = (
        "PAUTA: 01- Aprovação da Ata: 28/03/2025. Em discussão. Aprovada a unanimidade. "
        "02- Proc. digital n PROCESSO_30995. Eleição da coordenação. Aprovado e encaminhado “ad referendum”. "
        "03) Proc. digital n PROCESSO_30994. Eleição da coordenação."
    )
    itens = detectar_itens_car(texto)
    assert [i.numero_item for i in itens] == ["01", "02", "03"]
    assert itens[1].texto.startswith("02- Proc. digital")


def test_detectar_itens_car_hifen_de_um_digito_ou_no_meio_da_frase_nao_vira_item():
    texto = "PAUTA: 1) Item com Resolução nº 66- CEPE e prazo 5- Dias citados. 2) Outro item."
    itens = detectar_itens_car(texto)
    assert [i.numero_item for i in itens] == ["1", "2"]


def test_detectar_itens_car_texto_antes_do_primeiro_marcador_vira_item():
    texto = (
        "PAUTA: Aprovação das Atas: 30/09 e 10/10/2025. Em discussão. Não havendo manifestação "
        "contraria foram colocadas em votação. Aprovadas a unanimidade. 02) Proc. digital n PROCESSO_1. Outro."
    )
    itens = detectar_itens_car(texto)
    assert [i.numero_item for i in itens] == ["SN1", "02"]
    assert itens[0].texto.startswith("Aprovação das Atas")


BLOCO_AD_REFERENDA = (
    "O professor PESSOA_1 iniciou a reunião com a apreciação das aprovações por meio de Ad referenda, "
    "quais sejam: Relatório de concessão de Licença para Capacitação do professor PESSOA_2. Após "
    "apreciação, foi aprovado por unanimidade. Processo seletivo para professor substituto, em "
    "decorrência do afastamento para pós-doutoramento da professora PESSOA_3. Aprovado por unanimidade. "
)


def test_segmentar_texto_lacuna_antes_do_primeiro_item_vira_item_sem_numero():
    texto = "Havendo número legal, deu início à reunião. Em Pauta: " + BLOCO_AD_REFERENDA + (
        "COMUNICAÇÕES: com a palavra a professora PESSOA_4 comunicou que foi aberto edital. "
        "PROCESSOS/PROJETOS: [1] Solicitação de licença. Aprovado."
    )
    itens, _ = segmentar_texto("B", "CEFD", texto)
    assert [(i.secao, i.numero_item) for i in itens][0] == (SECAO_PAUTA, "SN1")
    assert "Processo seletivo para professor substituto" in itens[0].texto
    assert itens[0].texto.startswith("O professor PESSOA_1")


def test_segmentar_texto_abertura_curta_terminada_em_dois_pontos_nao_vira_item():
    texto = (
        "EM PAUTA: Com a palavra, o professor PESSOA_1 iniciou a reunião com a apreciação das "
        "solicitações aprovadas por meio de ad-referendum: [1] Solicitação de autorização. Aprovado. "
        "PROCESSOS/PROJETOS: [1] Outro processo. Aprovado."
    )
    itens, _ = segmentar_texto("B", "CEFD", texto)
    assert all(not i.numero_item.startswith("SN") for i in itens)


def test_segmentar_texto_lacuna_entre_itens_vira_item_com_secao_do_cabecalho():
    texto = (
        "1. APROVAÇÃO DE ATA: 1.1 Ata da reunião anterior. Aprovada por unanimidade. "
        "2. COMUNICAÇÃO: O Presidente comunicou que a Diretora do Centro retornará das férias no dia "
        "5 de março e que o calendário de reuniões do semestre será enviado aos conselheiros na "
        "próxima semana, com as datas propostas pela secretaria. "
        "3. ORDEM DO DIA: 3.1 Processo digital nº PROCESSO_1. Aprovado por unanimidade."
    )
    itens, _ = segmentar_texto("B", "CCAE", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_APROVACAO_ATA, "1.1"),
        (SECAO_COMUNICACOES, "SN1"),
        (SECAO_ORDEM_DO_DIA, "3.1"),
    ]


def test_segmentar_texto_encerramento_nao_vira_item():
    texto = (
        "1. ORDEM DO DIA: 1.1 Item único aprovado por unanimidade. Nada mais havendo a tratar, "
        "o Presidente encerrou a sessão, e eu, secretária, lavrei a presente ata, que após lida e "
        "aprovada segue assinada pelos presentes, com as assinaturas de todos os membros do conselho "
        "e da secretaria geral do centro, no dia e local indicados acima."
    )
    itens, _ = segmentar_texto("A", "CCENS", texto)
    assert [i.numero_item for i in itens] == ["1.1"]


def test_segmentar_texto_palavra_pauta_no_meio_da_frase_nao_e_cabecalho():
    texto = (
        "1. APROVAÇÃO DE ATA: 1.1 Ata da reunião anterior. Aprovada por unanimidade. "
        "2. EXPEDIENTE: inclusão, exclusão ou inversão de pauta. Inclusão: 3.04 Processo digital nº "
        "PROCESSO_1. Homologação da designação de coordenação; 3.05 Processo digital nº PROCESSO_2, "
        "renumerando os demais pontos da pauta conforme a solicitação da direção. "
        "3. PAUTA: 3.01 Aprovação de ata. Aprovada."
    )
    itens, _ = segmentar_texto("B", "CCHN", texto)
    lacuna = [i for i in itens if i.numero_item.startswith("SN")]
    assert [(i.secao, i.numero_item) for i in lacuna] == [(SECAO_EXPEDIENTE, "SN1")]
