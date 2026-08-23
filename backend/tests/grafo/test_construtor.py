from datetime import date

from app.grafo.cliente import executar_escrita, executar_leitura, obter_driver
from app.grafo.construtor import criar_no_ata, limpar_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def _documento_teste():
    return Documento(
        id_documento=999001, nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 6, 6), texto_limpo="texto",
    )


def test_criar_no_ata_cria_ata_centro_e_data():
    documento = Documento(
        id_documento=999001, nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 6, 6), texto_limpo="texto",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, documento)

        resultado = executar_leitura(
            driver,
            "MATCH (a:Ata {documento_id: $id})-[:PERTENCE_A]->(c:Centro) "
            "MATCH (a)-[:POSSUI]->(d:Data) RETURN c.sigla AS centro, d.valor AS data",
            id=999001,
        )
        assert resultado == [{"centro": "CT", "data": "2025-06-06"}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_no_ata_com_departamento():
    documento = Documento(
        id_documento=999002, nome_arquivo="y.pdf", url_origem="y.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", departamento="DCC", data_reuniao=date(2025, 7, 7), texto_limpo="texto",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, documento)

        resultado = executar_leitura(
            driver,
            "MATCH (a:Ata {documento_id: $id})-[:PERTENCE_A]->(dep:Departamento) RETURN dep.sigla AS departamento",
            id=999002,
        )
        assert resultado == [{"departamento": "DCC"}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_no_item_cria_item_e_menciona_processo():
    from app.grafo.construtor import criar_no_item

    item = ItemPauta(
        documento_id=999001, item_id_canonico="999001_PAUTA_2", secao="PAUTA", numero_item="2",
        texto="PAUTA 2: Processo digital nº PROCESSO_0042 - Interrupção de licença.",
        pagina_inicio=1, pagina_fim=1,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item)

        resultado = executar_leitura(
            driver,
            "MATCH (:Ata {documento_id: 999001})-[:CONTEM]->(i:ItemPauta {item_id_canonico: $id})"
            "-[:MENCIONA]->(p:Processo) RETURN p.token AS token",
            id="999001_PAUTA_2",
        )
        assert resultado == [{"token": "PROCESSO_0042"}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_agrupar_assuntos_por_processo_compartilhado():
    from app.grafo.construtor import agrupar_assuntos

    item1 = ItemPauta(
        item_id_canonico="1_A", documento_id=1, secao="PAUTA", numero_item="1",
        texto="PROCESSO_0001 assunto x", assunto="Reforma do prédio",
    )
    item2 = ItemPauta(
        item_id_canonico="2_A", documento_id=2, secao="PAUTA", numero_item="1",
        texto="PROCESSO_0001 mesmo processo", assunto="Texto completamente diferente",
    )
    item3 = ItemPauta(
        item_id_canonico="3_A", documento_id=3, secao="PAUTA", numero_item="1",
        texto="sem processo", assunto="Assunto isolado",
    )

    agrupamento = agrupar_assuntos([item1, item2, item3])

    grupos = list(agrupamento.values())
    assert sorted(len(g) for g in grupos) == [1, 2]
    grupo_com_dois = next(g for g in grupos if len(g) == 2)
    assert {i.item_id_canonico for i in grupo_com_dois} == {"1_A", "2_A"}


def test_agrupar_assuntos_por_texto_normalizado_identico():
    from app.grafo.construtor import agrupar_assuntos

    item1 = ItemPauta(
        item_id_canonico="1_B", documento_id=1, secao="PAUTA", numero_item="1",
        texto="sem processo", assunto="Aprovação do Calendário Acadêmico",
    )
    item2 = ItemPauta(
        item_id_canonico="2_B", documento_id=2, secao="PAUTA", numero_item="1",
        texto="sem processo", assunto="aprovação do calendário acadêmico",
    )

    agrupamento = agrupar_assuntos([item1, item2])

    assert len(agrupamento) == 1


def test_criar_nos_assunto_cria_relacoes_trata_de(db_session):
    from app.grafo.construtor import agrupar_assuntos, criar_no_item, criar_nos_assunto

    documento1 = Documento(
        id_documento=999001, nome_arquivo="x.pdf", url_origem="x.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 6, 6), texto_limpo="texto",
    )
    documento2 = Documento(
        id_documento=999002, nome_arquivo="y.pdf", url_origem="y.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 6, 13), texto_limpo="texto",
    )
    item1 = ItemPauta(
        item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: PROCESSO_0099 assunto", assunto="Reforma do laboratório",
        pagina_inicio=1, pagina_fim=1,
    )
    item2 = ItemPauta(
        item_id_canonico="999002_PAUTA_1", documento_id=999002, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: PROCESSO_0099 mesmo processo", assunto="Texto diferente",
        pagina_inicio=1, pagina_fim=1,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, documento1)
        criar_no_ata(driver, documento2)
        criar_no_item(driver, 999001, item1)
        criar_no_item(driver, 999002, item2)

        agrupamento = agrupar_assuntos([item1, item2])
        criar_nos_assunto(driver, agrupamento)

        resultado = executar_leitura(
            driver, "MATCH (:Assunto)<-[:TRATA_DE]-(i:ItemPauta) RETURN count(i) AS total"
        )
        assert resultado == [{"total": 2}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_nos_assunto_com_pagina_inicio_none_nao_levanta_excecao():
    from app.grafo.construtor import agrupar_assuntos, criar_nos_assunto

    item1 = ItemPauta(
        item_id_canonico="999003_PAUTA_1", documento_id=999003, secao="PAUTA", numero_item="1",
        texto="PROCESSO_0077 assunto", assunto="Assunto sem pagina registrada",
        pagina_inicio=None, pagina_fim=None,
    )
    item2 = ItemPauta(
        item_id_canonico="999004_PAUTA_1", documento_id=999004, secao="PAUTA", numero_item="1",
        texto="PROCESSO_0077 mesmo processo", assunto="Texto diferente",
        pagina_inicio=3, pagina_fim=3,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        for item in (item1, item2):
            executar_escrita(driver, "MERGE (:ItemPauta {item_id_canonico: $id})", id=item.item_id_canonico)

        agrupamento = agrupar_assuntos([item1, item2])
        criar_nos_assunto(driver, agrupamento)

        resultado = executar_leitura(
            driver, "MATCH (:Assunto)<-[:TRATA_DE]-(i:ItemPauta) RETURN count(i) AS total"
        )
        assert resultado == [{"total": 2}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_nos_assunto_pula_grupo_sem_assunto():
    from app.grafo.construtor import agrupar_assuntos, criar_nos_assunto

    item = ItemPauta(
        item_id_canonico="999005_PAUTA_1", documento_id=999005, secao="PAUTA", numero_item="1",
        texto="sem processo e sem assunto", assunto=None, pagina_inicio=1, pagina_fim=1,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        executar_escrita(driver, "MERGE (:ItemPauta {item_id_canonico: $id})", id=item.item_id_canonico)

        agrupamento = agrupar_assuntos([item])
        criar_nos_assunto(driver, agrupamento)

        resultado = executar_leitura(driver, "MATCH (s:Assunto) RETURN count(s) AS total")
        assert resultado == [{"total": 0}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_no_item_com_pagina_inicio_none_nao_levanta_excecao():
    from app.grafo.construtor import criar_no_item

    item = ItemPauta(
        documento_id=999006, item_id_canonico="999006_PAUTA_1", secao="PAUTA", numero_item="1",
        texto="PAUTA 1: Processo digital nº PROCESSO_0055 - Interrupção de licença.",
        pagina_inicio=None, pagina_fim=None,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item)

        resultado = executar_leitura(
            driver,
            "MATCH (i:ItemPauta {item_id_canonico: $id})-[:MENCIONA]->(p:Processo) RETURN p.token AS token",
            id="999006_PAUTA_1",
        )
        assert resultado == [{"token": "PROCESSO_0055"}]
    finally:
        limpar_grafo(driver)
        driver.close()
