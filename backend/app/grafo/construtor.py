from __future__ import annotations

from neo4j import Driver

from app.grafo.cliente import executar_escrita
from app.models.documento import Documento


def limpar_grafo(driver: Driver) -> None:
    executar_escrita(driver, "MATCH (n) DETACH DELETE n")


def criar_no_ata(driver: Driver, documento: Documento) -> None:
    executar_escrita(
        driver,
        """
        MERGE (a:Ata {documento_id: $documento_id})
        SET a.nome_arquivo = $nome_arquivo, a.tipo_orgao = $tipo_orgao
        MERGE (c:Centro {sigla: $centro})
        MERGE (a)-[:PERTENCE_A]->(c)
        MERGE (d:Data {valor: $data_reuniao})
        MERGE (a)-[:POSSUI]->(d)
        """,
        documento_id=documento.id_documento, nome_arquivo=documento.nome_arquivo,
        tipo_orgao=documento.tipo_orgao, centro=documento.centro,
        data_reuniao=documento.data_reuniao.isoformat(),
    )
    if documento.departamento:
        executar_escrita(
            driver,
            "MATCH (a:Ata {documento_id: $documento_id}) "
            "MERGE (dep:Departamento {sigla: $departamento}) "
            "MERGE (a)-[:PERTENCE_A]->(dep)",
            documento_id=documento.id_documento, departamento=documento.departamento,
        )
