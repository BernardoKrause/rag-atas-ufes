from datetime import date

from app.grafo.cliente import executar_escrita, executar_leitura, obter_driver
from app.grafo.construtor import UnionFind, criar_no_ata, limpar_grafo
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


def test_union_find_suporta_cadeia_longa_sem_estourar_recursao():
    uniao = UnionFind()
    for i in range(5000):
        uniao.union(str(i), str(i + 1))

    assert uniao.find("0") == uniao.find("5000")


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


def test_criar_no_ata_propaga_status_aprovacao():
    documento = Documento(
        id_documento=999003, nome_arquivo="z.pdf", url_origem="z.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 8, 8), texto_limpo="texto",
        status_aprovacao="pendente_aprovacao",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, documento)

        resultado = executar_leitura(
            driver,
            "MATCH (a:Ata {documento_id: $id}) RETURN a.status_aprovacao AS status",
            id=999003,
        )
        assert resultado == [{"status": "pendente_aprovacao"}]
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


def test_agrupar_assuntos_ignora_assunto_degenerado_como_sinal_fraco():
    from app.grafo.construtor import agrupar_assuntos

    # valores como "4" ou "Foi apreciada e" sao residuo de segmentacao, nao
    # assunto: no corpus real o valor "4" sozinho juntava 12 itens de atas
    # diferentes num unico componente.
    itens = [
        ItemPauta(
            item_id_canonico=f"{i}_C", documento_id=i, secao="COMUNICACOES", numero_item="4",
            texto="sem processo", assunto="4",
        )
        for i in range(1, 4)
    ] + [
        ItemPauta(
            item_id_canonico=f"{i}_D", documento_id=i, secao="PAUTA", numero_item="1",
            texto="sem processo", assunto="Foi apreciada e",
        )
        for i in range(4, 6)
    ]

    agrupamento = agrupar_assuntos(itens)

    assert len(agrupamento) == len(itens)


def test_agrupar_assuntos_ignora_degenerado_mas_mantem_sinal_forte_de_processo():
    from app.grafo.construtor import agrupar_assuntos

    item1 = ItemPauta(
        item_id_canonico="1_E", documento_id=1, secao="PAUTA", numero_item="4",
        texto="PROCESSO_0009 x", assunto="4",
    )
    item2 = ItemPauta(
        item_id_canonico="2_E", documento_id=2, secao="PAUTA", numero_item="4",
        texto="PROCESSO_0009 y", assunto="4",
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


def test_criar_no_deliberacao_cria_deliberacao_e_encaminhamento(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item

    item = ItemPauta(
        item_id_canonico="999001_PAUTA_3", documento_id=999001, secao="PAUTA", numero_item="3",
        texto="PAUTA 3: texto", tipo_desfecho="Aprovado", resultado_votacao="unanimidade",
        encaminhamento="publicar no boletim", ato_emitido="RESOLUCAO_79_2025", pagina_inicio=2,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item)
        criar_no_deliberacao(driver, item)

        resultado = executar_leitura(
            driver,
            "MATCH (:ItemPauta {item_id_canonico: $id})-[:GERA]->(del:Deliberação)-[:GERA]->(enc:Encaminhamento) "
            "RETURN del.tipo_desfecho AS desfecho, del.ato_emitido AS ato, enc.texto AS encaminhamento",
            id="999001_PAUTA_3",
        )
        assert resultado == [{"desfecho": "Aprovado", "ato": "RESOLUCAO_79_2025", "encaminhamento": "publicar no boletim"}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_no_deliberacao_com_resultado_votacao_e_ato_emitido_none(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item

    item = ItemPauta(
        item_id_canonico="999001_PAUTA_4", documento_id=999001, secao="PAUTA", numero_item="4",
        texto="PAUTA 4: texto", tipo_desfecho="Aprovado", resultado_votacao=None,
        encaminhamento=None, ato_emitido=None, pagina_inicio=3,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item)
        criar_no_deliberacao(driver, item)

        resultado = executar_leitura(
            driver,
            "MATCH (:ItemPauta {item_id_canonico: $id})-[:GERA]->(del:Deliberação) "
            "RETURN del.tipo_desfecho AS desfecho, del.resultado_votacao AS resultado, del.ato_emitido AS ato",
            id="999001_PAUTA_4",
        )
        assert resultado == [{"desfecho": "Aprovado", "resultado": None, "ato": None}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_no_deliberacao_pula_quando_tipo_desfecho_none(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item

    item = ItemPauta(
        item_id_canonico="999001_PAUTA_5", documento_id=999001, secao="PAUTA", numero_item="5",
        texto="PAUTA 5: texto", tipo_desfecho=None, resultado_votacao=None,
        encaminhamento=None, ato_emitido=None, pagina_inicio=4,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item)
        criar_no_deliberacao(driver, item)

        resultado = executar_leitura(
            driver,
            "MATCH (:ItemPauta {item_id_canonico: $id})-[:GERA]->(del:Deliberação) RETURN count(del) AS total",
            id="999001_PAUTA_5",
        )
        assert resultado == [{"total": 0}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_no_deliberacao_pula_encaminhamento_quando_falsy(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item

    item = ItemPauta(
        item_id_canonico="999001_PAUTA_6", documento_id=999001, secao="PAUTA", numero_item="6",
        texto="PAUTA 6: texto", tipo_desfecho="Aprovado", resultado_votacao="unanimidade",
        encaminhamento=None, ato_emitido="RESOLUCAO_80_2025", pagina_inicio=5,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item)
        criar_no_deliberacao(driver, item)

        resultado_deliberacao = executar_leitura(
            driver,
            "MATCH (:ItemPauta {item_id_canonico: $id})-[:GERA]->(del:Deliberação) RETURN count(del) AS total",
            id="999001_PAUTA_6",
        )
        assert resultado_deliberacao == [{"total": 1}]

        resultado_encaminhamento = executar_leitura(
            driver,
            "MATCH (:ItemPauta {item_id_canonico: $id})-[:GERA]->(del:Deliberação)-[:GERA]->(enc:Encaminhamento) RETURN count(enc) AS total",
            id="999001_PAUTA_6",
        )
        assert resultado_encaminhamento == [{"total": 0}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_resolver_citacoes_deliberacao_cria_relacao_revoga(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item, resolver_citacoes_deliberacao

    item_antigo = ItemPauta(
        item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: texto antigo", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_62_2024",
    )
    item_novo = ItemPauta(
        item_id_canonico="999001_PAUTA_5", documento_id=999001, secao="PAUTA", numero_item="5",
        texto="PAUTA 5: Baixada a RESOLUÇÃO NÚMERO SETENTA E NOVE. Revoga-se a Resolução nº 62, de 21 de fevereiro de 2024.",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_79_2025",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        for item in (item_antigo, item_novo):
            criar_no_item(driver, 999001, item)
            criar_no_deliberacao(driver, item)

        resolver_citacoes_deliberacao(driver, [item_antigo, item_novo])

        resultado = executar_leitura(
            driver,
            "MATCH (nova:Deliberação {item_id_canonico: '999001_PAUTA_5'})-[:revoga]->(antiga:Deliberação) "
            "RETURN antiga.item_id_canonico AS id",
        )
        assert resultado == [{"id": "999001_PAUTA_1"}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_resolver_citacoes_deliberacao_cria_relacao_altera_com_ano_barra(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item, resolver_citacoes_deliberacao

    item_antigo = ItemPauta(
        item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: texto antigo", tipo_desfecho="Aprovado", ato_emitido="DECISAO_50_2024",
    )
    item_novo = ItemPauta(
        item_id_canonico="999001_PAUTA_5", documento_id=999001, secao="PAUTA", numero_item="5",
        texto="PAUTA 5: Altera-se a Decisão Nº 50/2024 conforme deliberado.",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_79_2025",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        for item in (item_antigo, item_novo):
            criar_no_item(driver, 999001, item)
            criar_no_deliberacao(driver, item)

        resolver_citacoes_deliberacao(driver, [item_antigo, item_novo])

        resultado = executar_leitura(
            driver,
            "MATCH (nova:Deliberação {item_id_canonico: '999001_PAUTA_5'})-[:altera]->(antiga:Deliberação) "
            "RETURN antiga.item_id_canonico AS id",
        )
        assert resultado == [{"id": "999001_PAUTA_1"}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_resolver_citacoes_deliberacao_nao_cria_relacao_quando_ato_citado_nao_existe(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item, resolver_citacoes_deliberacao

    item_novo = ItemPauta(
        item_id_canonico="999001_PAUTA_5", documento_id=999001, secao="PAUTA", numero_item="5",
        texto="PAUTA 5: Revoga-se a Resolução nº 999, de 1 de janeiro de 2020.",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_79_2025",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        criar_no_item(driver, 999001, item_novo)
        criar_no_deliberacao(driver, item_novo)

        resolver_citacoes_deliberacao(driver, [item_novo])

        resultado = executar_leitura(
            driver,
            "MATCH (:Deliberação {item_id_canonico: '999001_PAUTA_5'})-[r:revoga]->() RETURN count(r) AS total",
        )
        assert resultado == [{"total": 0}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_resolver_citacoes_deliberacao_com_ato_duplicado_cria_uma_unica_relacao(db_session):
    from app.grafo.construtor import criar_no_deliberacao, criar_no_item, resolver_citacoes_deliberacao

    # no corpus real DECISAO_32_2025 e DECISAO_34_2025 aparecem em dois itens
    # cada (extracao imprecisa a montante): o MATCH casaria os dois nos e o
    # MERGE criaria duas arestas, uma delas necessariamente errada.
    itens_antigos = [
        ItemPauta(
            item_id_canonico=f"999001_PAUTA_{n}", documento_id=999001, secao="PAUTA", numero_item=str(n),
            texto=f"PAUTA {n}: texto antigo", tipo_desfecho="Aprovado", ato_emitido="DECISAO_32_2025",
        )
        for n in (1, 2)
    ]
    item_novo = ItemPauta(
        item_id_canonico="999001_PAUTA_5", documento_id=999001, secao="PAUTA", numero_item="5",
        texto="PAUTA 5: Revoga-se a Decisão nº 32/2025 deste Conselho.",
        tipo_desfecho="Aprovado", ato_emitido="DECISAO_90_2025",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        for item in [*itens_antigos, item_novo]:
            criar_no_item(driver, 999001, item)
            criar_no_deliberacao(driver, item)

        resolver_citacoes_deliberacao(driver, [*itens_antigos, item_novo])

        resultado = executar_leitura(
            driver,
            "MATCH (:Deliberação {item_id_canonico: '999001_PAUTA_5'})-[r:revoga]->() RETURN count(r) AS total",
        )
        assert resultado == [{"total": 1}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_relacao_mesmo_assunto_liga_deliberacoes_do_mesmo_grupo(db_session):
    from app.grafo.construtor import agrupar_assuntos, criar_no_deliberacao, criar_no_item, criar_relacao_mesmo_assunto

    item_a = ItemPauta(
        item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: menciona PROCESSO_2024001", assunto="Bolsas de pesquisa",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_1_2024",
    )
    item_b = ItemPauta(
        item_id_canonico="999001_PAUTA_2", documento_id=999001, secao="PAUTA", numero_item="2",
        texto="PAUTA 2: retoma PROCESSO_2024001", assunto="Bolsas de pesquisa",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_2_2024",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        for item in (item_a, item_b):
            criar_no_item(driver, 999001, item)
            criar_no_deliberacao(driver, item)

        agrupamento = agrupar_assuntos([item_a, item_b])
        criar_relacao_mesmo_assunto(driver, agrupamento)

        resultado = executar_leitura(
            driver,
            "MATCH (:Deliberação {item_id_canonico: '999001_PAUTA_1'})"
            "-[:trata_do_mesmo_assunto]->(:Deliberação {item_id_canonico: '999001_PAUTA_2'}) "
            "RETURN count(*) AS total",
        )
        assert resultado == [{"total": 1}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_criar_relacao_mesmo_assunto_nao_liga_quando_so_um_item_tem_deliberacao(db_session):
    from app.grafo.construtor import agrupar_assuntos, criar_no_deliberacao, criar_no_item, criar_relacao_mesmo_assunto

    item_a = ItemPauta(
        item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: menciona PROCESSO_2024001", assunto="Bolsas de pesquisa",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_1_2024",
    )
    item_b = ItemPauta(
        item_id_canonico="999001_PAUTA_2", documento_id=999001, secao="PAUTA", numero_item="2",
        texto="PAUTA 2: retoma PROCESSO_2024001", assunto="Bolsas de pesquisa",
        tipo_desfecho=None,
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        criar_no_ata(driver, _documento_teste())
        for item in (item_a, item_b):
            criar_no_item(driver, 999001, item)
            criar_no_deliberacao(driver, item)

        agrupamento = agrupar_assuntos([item_a, item_b])
        criar_relacao_mesmo_assunto(driver, agrupamento)

        resultado = executar_leitura(
            driver, "MATCH ()-[r:trata_do_mesmo_assunto]->() RETURN count(r) AS total",
        )
        assert resultado == [{"total": 0}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_construir_grafo_ponta_a_ponta(db_session):
    from app.models.item_pauta import ItemPauta
    from app.grafo.construtor import construir_grafo

    documento = _documento_teste()
    itens = [
        ItemPauta(
            item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
            texto="PAUTA 1: PROCESSO_0001 texto. Decisão: Aprovado(a).",
            assunto="Reforma", tipo_desfecho="Aprovado",
        ),
    ]

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        construir_grafo([(documento, itens)], driver)

        resultado = executar_leitura(
            driver,
            "MATCH (:Ata)-[:CONTEM]->(i:ItemPauta)-[:GERA]->(:Deliberação) RETURN count(i) AS total",
        )
        assert resultado == [{"total": 1}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_construir_grafo_cria_relacoes_cross_documento(db_session):
    from app.models.item_pauta import ItemPauta
    from app.grafo.construtor import construir_grafo

    documento1 = Documento(
        id_documento=999007, nome_arquivo="a.pdf", url_origem="a.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 8, 1), texto_limpo="texto",
    )
    documento2 = Documento(
        id_documento=999008, nome_arquivo="b.pdf", url_origem="b.pdf", centro="CT", campus="Goiabeiras",
        tipo_orgao="B", orgao="CT", data_reuniao=date(2025, 8, 8), texto_limpo="texto",
    )
    item1 = ItemPauta(
        item_id_canonico="999007_PAUTA_1", documento_id=999007, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: menciona PROCESSO_2024001 texto.", assunto="Bolsas de pesquisa",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_1_2025",
    )
    item2 = ItemPauta(
        item_id_canonico="999008_PAUTA_1", documento_id=999008, secao="PAUTA", numero_item="1",
        texto="PAUTA 1: retoma PROCESSO_2024001 texto.", assunto="Bolsas de pesquisa",
        tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_2_2025",
    )

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        construir_grafo([(documento1, [item1]), (documento2, [item2])], driver)

        resultado_assunto = executar_leitura(
            driver,
            "MATCH (i1:ItemPauta {item_id_canonico: $id1})-[:TRATA_DE]->(s:Assunto)"
            "<-[:TRATA_DE]-(i2:ItemPauta {item_id_canonico: $id2}) RETURN count(s) AS total",
            id1="999007_PAUTA_1", id2="999008_PAUTA_1",
        )
        assert resultado_assunto == [{"total": 1}]

        resultado_mesmo_assunto = executar_leitura(
            driver,
            "MATCH (:Deliberação {item_id_canonico: $id1})-[:trata_do_mesmo_assunto]->"
            "(:Deliberação {item_id_canonico: $id2}) RETURN count(*) AS total",
            id1="999007_PAUTA_1", id2="999008_PAUTA_1",
        )
        assert resultado_mesmo_assunto == [{"total": 1}]
    finally:
        limpar_grafo(driver)
        driver.close()


def _fragmentos_do_mesmo_item():
    return [
        ItemPauta(
            item_id_canonico="999001_PAUTA_1", documento_id=999001, secao="PAUTA", numero_item="1",
            ocorrencia_indice=0, fragmento_indice=indice,
            texto="PAUTA 1: menciona PROCESSO_2024001", assunto="Bolsas de pesquisa",
            tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_1_2024", encaminhamento="publicar",
        ) if indice == 0 else ItemPauta(
            item_id_canonico=f"999001_PAUTA_1_F{indice}", documento_id=999001, secao="PAUTA", numero_item="1",
            ocorrencia_indice=0, fragmento_indice=indice,
            texto="continuacao PROCESSO_2024001", assunto="Bolsas de pesquisa",
            tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_1_2024", encaminhamento="publicar",
        )
        for indice in range(3)
    ]


def test_construir_grafo_cria_deliberacao_so_no_primeiro_fragmento(db_session):
    from app.grafo.construtor import construir_grafo

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        construir_grafo([(_documento_teste(), _fragmentos_do_mesmo_item())], driver)

        deliberacoes = executar_leitura(
            driver, "MATCH (d:Deliberação) RETURN d.item_id_canonico AS id",
        )
        encaminhamentos = executar_leitura(
            driver, "MATCH (e:Encaminhamento) RETURN count(e) AS total",
        )
        itens = executar_leitura(driver, "MATCH (i:ItemPauta) RETURN count(i) AS total")
        assert deliberacoes == [{"id": "999001_PAUTA_1"}]
        assert encaminhamentos == [{"total": 1}]
        assert itens == [{"total": 3}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_construir_grafo_fragmentos_seguintes_alcancam_a_deliberacao_do_primeiro(db_session):
    from app.grafo.construtor import construir_grafo

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        construir_grafo([(_documento_teste(), _fragmentos_do_mesmo_item())], driver)

        resultado = executar_leitura(
            driver,
            "MATCH (i:ItemPauta)-[:GERA]->(d:Deliberação) "
            "RETURN i.item_id_canonico AS item, d.item_id_canonico AS del ORDER BY item",
        )
        assert resultado == [
            {"item": "999001_PAUTA_1", "del": "999001_PAUTA_1"},
            {"item": "999001_PAUTA_1_F1", "del": "999001_PAUTA_1"},
            {"item": "999001_PAUTA_1_F2", "del": "999001_PAUTA_1"},
        ]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_construir_grafo_nao_liga_mesmo_assunto_entre_fragmentos_do_mesmo_item(db_session):
    from app.grafo.construtor import construir_grafo

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        construir_grafo([(_documento_teste(), _fragmentos_do_mesmo_item())], driver)

        resultado = executar_leitura(
            driver, "MATCH ()-[r:trata_do_mesmo_assunto]->() RETURN count(r) AS total",
        )
        assert resultado == [{"total": 0}]
    finally:
        limpar_grafo(driver)
        driver.close()


def test_construir_grafo_resolve_citacao_presente_em_fragmento_posterior(db_session):
    from app.grafo.construtor import construir_grafo

    antiga = ItemPauta(
        item_id_canonico="999001_PAUTA_9", documento_id=999001, secao="PAUTA", numero_item="9",
        texto="PAUTA 9: texto", tipo_desfecho="Aprovado", ato_emitido="RESOLUCAO_5_2020",
    )
    fragmentos = _fragmentos_do_mesmo_item()
    fragmentos[2].texto = "Revoga-se a Resolução nº 5/2020 do conselho."

    driver = obter_driver()
    try:
        limpar_grafo(driver)
        construir_grafo([(_documento_teste(), [antiga, *fragmentos])], driver)

        resultado = executar_leitura(
            driver,
            "MATCH (:Deliberação {item_id_canonico: '999001_PAUTA_1'})-[:revoga]->"
            "(:Deliberação {item_id_canonico: '999001_PAUTA_9'}) RETURN count(*) AS total",
        )
        assert resultado == [{"total": 1}]
    finally:
        limpar_grafo(driver)
        driver.close()
