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
    ItemDetectado,
    SOBREPOSICAO_FRAGMENTO,
    TAMANHO_MAX_FRAGMENTO,
    _neutralizar_numeracao_de_margem,
    _normalizar_com_mapa,
    _reclassificar_exclusao_de_pauta,
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


def test_familia_pontilhada_aceita_pauta_no_plural():
    # doc 588 do corpus real (CCAE): "3. PAUTAS: 3.1 - Documento avulso..."
    texto = "1. EXPEDIENTE: NÃO HOUVE. 3. PAUTAS: 3.1 – DOCUMENTO AVULSO Nº 123."
    itens = detectar_itens_familia_pontilhada(texto)
    assert (SECAO_PAUTA, "3.1") in [(i.secao, i.numero_item) for i in itens]


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


def test_familia_pontilhada_cabecalho_de_secao_sem_acento():
    # regressao: RE_SECAO_NUMERADA casa variantes sem acento (classes [CÇ]/
    # [AÃ]/[OÕ]) e variantes DA/DE + singular/plural que _ALIAS_SECAO nao
    # cobria, levantando KeyError em vez de reclassificar como APROVACAO_ATA
    texto = "1. APROVACAO DA ATA: 1.1 ATA ANTERIOR APROVADA."
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_APROVACAO_ATA, "1.1")]


def test_familia_pontilhada_cabecalho_de_secao_combinacao_nao_prevista_no_alias():
    # regressao: "APRECIAÇÃO DA ATA" (prefixo APRECIA + "DA" em vez de "DE")
    # bate no regex mas nao tinha entrada em _ALIAS_SECAO
    texto = "1. APRECIAÇÃO DA ATA: 1.1 ATA ANTERIOR APROVADA."
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_APROVACAO_ATA, "1.1")]


def test_familia_pontilhada_aceita_secao_sem_pontuacao_antes_do_subitem():
    # docs 609/611/612/613/600/603/607 do corpus real (CCAE): cabecalho de
    # secao vai direto pro subitem, sem ":" nem "." depois da palavra da
    # secao — ex. doc 613: "1. EXPEDIENTE Não houve. 2. ORDEM DO DIA 2.1
    # Aprovação do Calendário..."
    texto = (
        "1. EXPEDIENTE NÃO HOUVE. "
        "2. ORDEM DO DIA 2.1 APROVAÇÃO DO CALENDÁRIO DE REUNIÕES."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_ORDEM_DO_DIA, "2.1"),
    ]


def test_familia_pontilhada_secao_sem_pontuacao_e_sem_subitem_fica_vazia():
    # secao sem numeracao propria (ex.: "EXPEDIENTE" sem nada a tratar) nao
    # deve gerar item nenhum — mesmo edge case ja documentado em
    # detectar_itens_car
    texto = "1. EXPEDIENTE NÃO HOUVE."
    assert detectar_itens_familia_pontilhada(texto) == []


def test_familia_pontilhada_nao_trunca_secao_em_numero_coincidente_no_meio_da_frase():
    # regressao: com o terminador opcional, "43. COMUNICADOS" no meio de
    # uma frase (numero de resolucao seguido por uma palavra de secao)
    # nao pode ser lido como cabecalho de nova secao — so vale como
    # cabecalho se um subitem "N.M" vier logo em seguida (lookahead)
    texto = (
        "1. EXPEDIENTE: 1.1 LEITURA DA RESOLUCAO 43. COMUNICADOS FORAM FEITOS "
        "PELA DIRECAO. 1.2 OUTRO ITEM."
    )
    itens = detectar_itens_familia_pontilhada(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_EXPEDIENTE, "1.1"),
        (SECAO_EXPEDIENTE, "1.2"),
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


def test_detectar_itens_car_ignora_numero_citado_entre_aspas():
    # regressao: um item pode citar o numero de OUTRO item entre aspas como
    # referencia — isso nao pode ser confundido com o inicio de um item novo
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
        (SECAO_COMUNICACOES, "1"),
        (SECAO_COMUNICACOES, "2"),
        (SECAO_PROCESSOS_PROJETOS, "1"),
        (SECAO_PROCESSOS_PROJETOS, "2"),
    ]


def test_detectar_itens_cefd_secao_sem_itens_e_pulada():
    texto = "EM PAUTA: SEM ITENS NUMERADOS. PALAVRA LIVRE: NENHUM REGISTRO."
    assert detectar_itens_cefd(texto) == []


def test_cefd_aceita_ponto_final_em_vez_de_dois_pontos_no_cabecalho():
    # doc 438 do corpus real (CEFD): "PROCESSOS/PROJETOS. [1] Solicitação..."
    # em vez de "PROCESSOS/PROJETOS: [1] ..." — RE_SECAO_CEFD so aceitava ":"
    texto = "PROCESSOS/PROJETOS. [1] SOLICITAÇÃO DE AFASTAMENTO PARA DOUTORADO."
    itens = detectar_itens_cefd(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PROCESSOS_PROJETOS, "1"),
    ]


def test_detectar_itens_cce_ponto_numerado_com_ponto_final():
    texto = "DECLAROU ABERTA A SESSÃO. Ponto 01. Comunicações: TEXTO. Ponto 02. TEXTO DOIS."
    itens = detectar_itens_cce(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "01"),
        (SECAO_PAUTA, "02"),
    ]


def test_detectar_itens_cce_ordem_invertida_maiuscula_de_ata_antiga():
    # atas mais antigas do CCE usam "PONTO N –" tudo maiusculo, ou a ordem
    # invertida "Nº. Ponto –"
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
    # achado real doc 469: "2021/2." bate no padrao digito-ponto-espaco-
    # maiuscula do RE_ITEM_CE_D e criava um item fantasma duplicado "2"
    # antes do item real seguinte, cortando o texto do item anterior no meio
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
    # achado real doc 463: item 4 comeca com "5ª Conferência..." — o
    # lookahead so aceitava maiuscula direto apos "N. ", perdendo esse item
    texto = "INFORMES: 1. PRIMEIRO INFORME SOBRE O EVENTO. 2. 5ª CONFERÊNCIA MUNICIPAL DE EDUCAÇÃO."
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_INFORMES, "1"),
        (SECAO_INFORMES, "2"),
    ]


def test_ce_d_tenta_familia_pontilhada_primeiro_e_e_robusto_a_secao_extra():
    # achado real: ata_da_3a_reuniao_ordinaria_colped.pdf (fixture real, mesmo
    # colegiado dos docs 463/469) usa o formato pontilhado antigo ("1. APRE-
    # CIACAO DE ATA: 1.1 ..."), sem "INFORMES:"/"PAUTA." sem numero — se
    # ("D","CE") virasse so detectar_itens_ce_d sem fallback, essa fixture
    # real ia quebrar de 12 itens pra 0.
    #
    # A ordem em que os dois formatos sao tentados importa: tentar o formato
    # novo primeiro e cair pro pontilhado so quando o novo devolve vazio
    # parece seguro isoladamente, mas nao e — cabecalhos pontilhados como
    # "2. EXPEDIENTE:", "3. INFORMES:", "4. PAUTA:" batem parcialmente em
    # RE_ITEM_CE_D (o "N." no comeco) e podem produzir itens espurios em vez
    # de lista vazia dependendo de onde os limites de RE_SECAO_CE_D caem,
    # entao "resultado vazio do formato novo" nao e um sinal confiavel de
    # "formato antigo". Por isso a ordem certa e a inversa: tenta o
    # pontilhado primeiro (resultado NAO-vazio dele e que e o sinal
    # confiavel), so cai pro formato novo se o pontilhado vier vazio.
    #
    # Este teste replica a forma real da fixture (3 secoes pontilhadas) mais
    # uma 4a secao pontilhada extra no final ("5. PALAVRA LIVRE:") pra
    # provar que a ordem certa nao quebra nesse cenario.
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
    # achado real nos dois docs (463 e 469): a frase comum "Retirado de
    # pauta." / "Retirado de Pauta." aparece varias vezes como texto
    # narrativo comum (nao cabecalho de secao) e batia em RE_SECAO_CE_D
    # quando o regex era case-insensitive, cortando o item real ali no meio
    # e criando uma "secao" fantasma. Cabecalho real e sempre em CAIXA ALTA
    # ("INFORMES:", "PAUTA.") nos dois docs — o fix (case-sensitive) so deixa
    # passar exatamente essa forma.
    texto = (
        "PAUTA. 1. Primeiro item da pauta, retirado de pauta. "
        "2. Segundo item, com sucesso. Retirado de Pauta. Nada mais a tratar."
    )
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]
    # o item 2 deve conter a frase de encerramento inteira, sem cortar em
    # "Retirado de Pauta." como uma nova secao fantasma
    assert "Nada mais a tratar" in itens[1].texto


def test_ce_d_item_sem_espaco_apos_o_ponto():
    # achado real doc 463: item 4 da PAUTA e "4.Metodologia de trabalho..."
    # sem espaco (artefato de extracao de PDF) — confirmado via scan
    # completo dos dois docs reais por \d{1,2}\.[A-ZÀ-Ú] (unica ocorrencia)
    texto = "PAUTA. 1. PRIMEIRO ITEM. 2.Segundo item sem espaço após o ponto."
    itens = detectar_itens_ce_d(texto)
    assert [(i.secao, i.numero_item) for i in itens] == [
        (SECAO_PAUTA, "1"),
        (SECAO_PAUTA, "2"),
    ]


def test_ce_d_item_sem_espaco_nao_confunde_numeracao_de_dois_niveis():
    # a guarda contra "4.1" (nivel-dois da familia pontilhada) nao vem do
    # \s+ (agora \s*), vem do lookbehind (nao pode ser precedido de digito)
    # + do requisito de maiuscula/ordinal logo em seguida — "4.1 Aprovacao"
    # e "4.1. Aprovacao" nao devem virar item nenhum aqui
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
    # achado (a), parte CEUNES: reusa o mesmo detector do CT (INFORME N:/
    # PAUTA N:) — confirmado contra os 10 documentos reais nao-escaneados
    texto = "PAUTA 1: PRIMEIRO ITEM."
    itens, _ = segmentar_texto("B", "CEUNES", texto)
    assert [(i.secao, i.numero_item) for i in itens] == [(SECAO_PAUTA, "1")]


def test_ceunes_tipo_a_usa_mesmo_formato_informe_pauta_do_tipo_b():
    # achado do gap de 77 docs: CEUNES tipo A usa o mesmo formato "INFORME N:"
    # / "PAUTA N:" do tipo B, mas nao tinha entrada de dispatch propria —
    # caia no fallback ("A","*") -> familia_pontilhada, que nao bate nesse
    # formato (confirmado rodando RE_ITEM_CT contra os 53 docs reais nao
    # escaneados do grupo)
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
    # reconstroi o texto original removendo a sobreposicao, confirma que nada foi perdido
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
    # achado (c): numeracao duplicada na fonte (ou falso positivo de
    # deteccao) vira uma ocorrencia extra desambiguada por sufixo, em vez de
    # quebrar a constraint unica
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
    # regressao achado (c): numeracao genuinamente duplicada na fonte (dois
    # assuntos distintos com o mesmo numero_item, ex.: doc 456 do corpus
    # real) nao pode mais quebrar a constraint unica — vira ocorrencia_indice
    # crescente
    texto = "1. COMUNICAÇÕES: 1.1 PRIMEIRO ASSUNTO. 1.1 SEGUNDO ASSUNTO, NUMERO REPETIDO NA FONTE."
    documento = _criar_documento(db_session, texto_limpo=texto)
    itens = segmentar_e_persistir(documento, db_session)

    assert len(itens) == 2
    assert {i.ocorrencia_indice for i in itens} == {0, 1}
    assert {i.item_id_canonico for i in itens} == {
        f"{documento.id_documento}_COMUNICACOES_1.1",
        f"{documento.id_documento}_COMUNICACOES_1.1_D1",
    }


def test_segmentar_as_6_fixtures_reais_bate_com_contagem_manual(db_session):
    documentos = executar_pipeline(FIXTURES, SECRET_KEY_SEGMENTADOR, db_session)
    contagem_esperada = {
        "ata_da_1a_reuniao_ordinaria_-_db_ccens_04-02-2025.docx.pdf": 4,   # Tipo A
        # B1/CT: 27 itens estruturais, mas PAUTA 7 e 8 (votos em separado
        # extensos) sofrem overflow-split em 2 fragmentos cada -> 29
        "10-2025.pdf": 29,
        "ata_05_02_2025.pdf": 14,                                           # B2/CAR
        "1_ata_sessao_ordinaria_do_dia_28_de_janeiro_2025.pdf": 8,          # B3/CCAE
        "2020.08.17_-_ata_1a_ordinaria_camara_local.pdf": 7,                # Tipo C
        "ata_da_3a_reuniao_ordinaria_colped.pdf": 12,                       # Tipo D
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
    # CT/10-2025.pdf tem 8 paginas — confirma que o mapeamento de pagina
    # funciona de ponta a ponta (extrair_texto_bruto -> pipeline -> segmentador)
    documentos = executar_pipeline(FIXTURES, SECRET_KEY_SEGMENTADOR, db_session)
    ct = next(d for d in documentos if d.nome_arquivo == "10-2025.pdf")
    itens = segmentar_e_persistir(ct, db_session)

    assert all(i.pagina_inicio is not None for i in itens)
    paginas = {i.pagina_inicio for i in itens}
    assert len(paginas) > 1  # itens espalhados por mais de uma pagina
    assert min(paginas) == 1


def test_segmentar_documento_sem_paginas_offsets_deixa_pagina_nula(db_session):
    documento = _criar_documento(db_session, paginas_offsets=None, nome_arquivo="sem_paginas.pdf")
    itens = segmentar_e_persistir(documento, db_session)
    assert all(i.pagina_inicio is None and i.pagina_fim is None for i in itens)
