from datetime import date

from app.grafo.cliente import executar_leitura, obter_driver
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
