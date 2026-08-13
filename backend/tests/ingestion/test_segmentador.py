from app.ingestion.segmentador import (
    SECAO_APROVACAO_ATA,
    SECAO_COMUNICACOES,
    SECAO_EXCLUSAO_DE_PAUTA,
    SECAO_EXPEDIENTE,
    SECAO_INFORMES,
    SECAO_ORDEM_DO_DIA,
    SECAO_PAUTA,
    ItemDetectado,
    _neutralizar_numeracao_de_margem,
    _normalizar_com_mapa,
    _reclassificar_exclusao_de_pauta,
    detectar_itens_familia_pontilhada,
    detectar_itens_car,
    detectar_itens_ct,
)


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
    # o "C" normalizado (indice 3) deve apontar pro "C" original (indice 4)
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


def test_familia_pontilhada_ignora_numero_de_token_de_anonimizacao():
    # regressao: "PESSOA_12752." tem "52." no final, que sozinho parece um
    # inicio de secao numerada — nao pode disparar falso positivo
    texto = "REUNIÃO SOB A PRESIDÊNCIA DA PROFESSORA PESSOA_12752. INFORMES: PAUTA: 1) ITEM."
    itens = detectar_itens_familia_pontilhada(texto)
    assert itens == []


def test_familia_pontilhada_ignora_numero_citado_entre_aspas():
    # regressao: um item pode citar o numero de OUTRO item entre aspas
    # como referencia (ex.: revisar o topico "1.4" de uma ata anterior) —
    # isso nao e um novo item comecando
    texto = (
        '1. APRECIAÇÃO DE ATA: 1.1. A PROFESSORA SUGERIU A REVISÃO DO TÓPICO '
        '“1.4” DA ATA ANTERIOR. 2. EXPEDIENTE: 2.1 ITEM SEGUINTE.'
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_APROVACAO_ATA, "1.1"),
        (SECAO_EXPEDIENTE, "2.1"),
    ]


def test_neutralizar_numeracao_de_margem_remove_linha_so_com_digitos():
    texto = "PRIMEIRA LINHA\n8\nSEGUNDA LINHA\n9\nTERCEIRA LINHA"
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert len(resultado) == len(texto)
    assert "8" not in resultado
    assert "9" not in resultado
    assert "PRIMEIRA LINHA" in resultado


def test_neutralizar_numeracao_de_margem_preserva_numero_dentro_da_linha():
    texto = "1. ORDEM DO DIA: 1.1 ITEM.\n8\nCONTINUAÇÃO."
    resultado = _neutralizar_numeracao_de_margem(texto)
    assert "1. ORDEM DO DIA: 1.1 ITEM." in resultado


def test_reclassificar_exclusao_de_pauta():
    itens = [
        ItemDetectado(SECAO_EXPEDIENTE, "2.1", 0, 10, "EXCLUSÃO DE PAUTA: 2.1 ITEM RETIRADO."),
        ItemDetectado(SECAO_EXPEDIENTE, "2.2", 10, 20, "2.2 OUTRO ITEM, SEM RELAÇÃO COM EXCLUSÃO."),
    ]
    resultado = _reclassificar_exclusao_de_pauta(itens)
    assert resultado[0].secao == SECAO_EXCLUSAO_DE_PAUTA
    assert resultado[1].secao == SECAO_EXPEDIENTE


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
    # padding inconsistente no corpus real: "1)", "2)", "04)", "05)", "6)"...
    texto = "INFORMES: PAUTA: 1) PRIMEIRO ITEM. 2) SEGUNDO ITEM. 04) TERCEIRO ITEM COM PADDING."
    itens = detectar_itens_car(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
        (SECAO_PAUTA, "04"),
    ]


def test_detectar_itens_car_sem_pauta_retorna_vazio():
    assert detectar_itens_car("TEXTO SEM A PALAVRA PAUTA.") == []
