from app.core.config import settings
from app.grafo.cliente import executar_escrita, executar_leitura, obter_driver


def test_executar_escrita_e_leitura_ida_e_volta():
    driver = obter_driver()
    try:
        executar_escrita(driver, "MERGE (n:TesteEnriquecedor {chave: $chave})", chave="abc")
        resultado = executar_leitura(driver, "MATCH (n:TesteEnriquecedor {chave: $chave}) RETURN n.chave AS chave", chave="abc")
        assert resultado == [{"chave": "abc"}]
    finally:
        executar_escrita(driver, "MATCH (n:TesteEnriquecedor) DETACH DELETE n")
        driver.close()


def test_suite_usa_o_neo4j_de_teste_e_nao_o_de_desenvolvimento():
    assert settings.neo4j_uri.endswith(f":{settings.neo4j_teste_bolt_port}")
