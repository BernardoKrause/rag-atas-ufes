from datetime import date

from app.grafo.cliente import executar_leitura, obter_driver
from app.grafo.construtor import criar_no_ata, limpar_grafo
from app.models.documento import Documento


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
