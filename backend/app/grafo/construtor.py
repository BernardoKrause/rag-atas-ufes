from __future__ import annotations

import re

from neo4j import Driver

from app.grafo.cliente import executar_escrita
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta


RE_TOKEN_PROCESSO = re.compile(r"PROCESSO_\d{4,}")


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


def criar_no_item(driver: Driver, documento_id: int, item: ItemPauta) -> None:
    executar_escrita(
        driver,
        """
        MATCH (a:Ata {documento_id: $documento_id})
        MERGE (i:ItemPauta {item_id_canonico: $item_id})
        SET i.secao = $secao, i.numero_item = $numero_item,
            i.pagina_inicio = $pagina_inicio, i.pagina_fim = $pagina_fim,
            i.trecho = $trecho
        MERGE (a)-[:CONTEM]->(i)
        """,
        documento_id=documento_id, item_id=item.item_id_canonico, secao=item.secao,
        numero_item=item.numero_item, pagina_inicio=item.pagina_inicio, pagina_fim=item.pagina_fim,
        trecho=item.texto[:500],
    )
    for token in set(RE_TOKEN_PROCESSO.findall(item.texto)):
        executar_escrita(
            driver,
            "MATCH (i:ItemPauta {item_id_canonico: $item_id}) "
            "MERGE (p:Processo {token: $token}) "
            "MERGE (i)-[:MENCIONA {pagina: $pagina, trecho: $trecho}]->(p)",
            item_id=item.item_id_canonico, token=token,
            pagina=item.pagina_inicio, trecho=item.texto[:500],
        )
