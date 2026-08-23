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
