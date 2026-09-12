from __future__ import annotations

from neo4j import Driver

from app.grafo.cliente import executar_leitura
from app.recuperacao.tipos import Hit


def expandir_grafo(ancoras: list[Hit], driver: Driver) -> list[Hit]:
    if not ancoras:
        return []

    linhas = executar_leitura(
        driver,
        """
        UNWIND $ancoras AS ancora
        MATCH (:ItemPauta {item_id_canonico: ancora.item_id})-[:TRATA_DE]->(:Assunto)
              <-[:TRATA_DE]-(relacionado:ItemPauta)
        WHERE relacionado.item_id_canonico <> ancora.item_id
        WITH relacionado.item_id_canonico AS item_id_canonico, min(ancora.rank) AS rank
        RETURN item_id_canonico, rank
        ORDER BY rank
        """,
        ancoras=[{"item_id": hit.item_id_canonico, "rank": hit.rank} for hit in ancoras],
    )

    ids_ancoras = {hit.item_id_canonico for hit in ancoras}
    return [
        Hit(item_id_canonico=linha["item_id_canonico"], rank=linha["rank"])
        for linha in linhas
        if linha["item_id_canonico"] not in ids_ancoras
    ]


def obter_contexto_grafo(item_id_canonico: str, driver: Driver) -> dict:
    linhas_base = executar_leitura(
        driver,
        """
        MATCH (i:ItemPauta {item_id_canonico: $item_id})
        OPTIONAL MATCH (a:Ata)-[:CONTEM]->(i)
        OPTIONAL MATCH (a)-[:PERTENCE_A]->(c:Centro)
        OPTIONAL MATCH (a)-[:PERTENCE_A]->(dep:Departamento)
        OPTIONAL MATCH (a)-[:POSSUI]->(d:Data)
        OPTIONAL MATCH (i)-[:GERA]->(del:Deliberação)
        OPTIONAL MATCH (del)-[:GERA]->(enc:Encaminhamento)
        RETURN c.sigla AS centro, dep.sigla AS departamento, d.valor AS data_reuniao,
               del.tipo_desfecho AS tipo_desfecho, del.resultado_votacao AS resultado_votacao,
               del.ato_emitido AS ato_emitido, enc.texto AS encaminhamento
        """,
        item_id=item_id_canonico,
    )
    linhas_relacionadas = executar_leitura(
        driver,
        """
        MATCH (:ItemPauta {item_id_canonico: $item_id})-[:GERA]->(del:Deliberação)
        CALL {
            WITH del
            MATCH (del)-[r:revoga|altera|substitui]->(outra:Deliberação)
            RETURN type(r) AS tipo_relacao, outra.item_id_canonico AS item_id_canonico,
                   outra.ato_emitido AS ato_emitido
            UNION
            WITH del
            MATCH (del)-[r:trata_do_mesmo_assunto]-(outra:Deliberação)
            RETURN type(r) AS tipo_relacao, outra.item_id_canonico AS item_id_canonico,
                   outra.ato_emitido AS ato_emitido
        }
        RETURN tipo_relacao, item_id_canonico, ato_emitido
        """,
        item_id=item_id_canonico,
    )

    base = linhas_base[0] if linhas_base else {}
    return {
        "centro": base.get("centro"),
        "departamento": base.get("departamento"),
        "data_reuniao": base.get("data_reuniao"),
        "tipo_desfecho": base.get("tipo_desfecho"),
        "resultado_votacao": base.get("resultado_votacao"),
        "ato_emitido": base.get("ato_emitido"),
        "encaminhamento": base.get("encaminhamento"),
        "deliberacoes_relacionadas": linhas_relacionadas,
    }
