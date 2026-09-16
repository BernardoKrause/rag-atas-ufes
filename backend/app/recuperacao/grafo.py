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
        CALL (ancora) {
            MATCH (:ItemPauta {item_id_canonico: ancora.item_id})-[:TRATA_DE]->(:Assunto)
                  <-[:TRATA_DE]-(relacionado:ItemPauta)
            WHERE relacionado.item_id_canonico <> ancora.item_id
            RETURN relacionado.item_id_canonico AS item_id_canonico
            UNION
            MATCH (:ItemPauta {item_id_canonico: ancora.item_id})-[:GERA]->(:Deliberação)
                  -[:revoga|altera|substitui]-(outra:Deliberação)
            RETURN outra.item_id_canonico AS item_id_canonico
        }
        WITH item_id_canonico, min(ancora.rank) AS rank
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


def obter_contextos_grafo(item_ids: list[str], driver: Driver) -> dict[str, dict]:
    if not item_ids:
        return {}

    linhas_base = executar_leitura(
        driver,
        """
        UNWIND $item_ids AS item_id
        OPTIONAL MATCH (i:ItemPauta {item_id_canonico: item_id})
        OPTIONAL MATCH (a:Ata)-[:CONTEM]->(i)
        OPTIONAL MATCH (a)-[:PERTENCE_A]->(c:Centro)
        OPTIONAL MATCH (a)-[:PERTENCE_A]->(dep:Departamento)
        OPTIONAL MATCH (a)-[:POSSUI]->(d:Data)
        OPTIONAL MATCH (i)-[:GERA]->(del:Deliberação)
        OPTIONAL MATCH (del)-[:GERA]->(enc:Encaminhamento)
        RETURN item_id, c.sigla AS centro, dep.sigla AS departamento, d.valor AS data_reuniao,
               del.tipo_desfecho AS tipo_desfecho, del.resultado_votacao AS resultado_votacao,
               del.ato_emitido AS ato_emitido, enc.texto AS encaminhamento
        """,
        item_ids=item_ids,
    )
    linhas_relacionadas = executar_leitura(
        driver,
        """
        UNWIND $item_ids AS item_id
        MATCH (:ItemPauta {item_id_canonico: item_id})-[:GERA]->(del:Deliberação)
        CALL (del) {
            MATCH (del)-[r:revoga|altera|substitui]->(outra:Deliberação)
            RETURN type(r) AS tipo_relacao, outra.item_id_canonico AS relacionado_id,
                   outra.ato_emitido AS ato_emitido
            UNION
            MATCH (outra:Deliberação)-[r:revoga|altera|substitui]->(del)
            RETURN
                CASE type(r)
                    WHEN 'revoga' THEN 'revogado_por'
                    WHEN 'altera' THEN 'alterado_por'
                    WHEN 'substitui' THEN 'substituido_por'
                END AS tipo_relacao,
                outra.item_id_canonico AS relacionado_id, outra.ato_emitido AS ato_emitido
            UNION
            MATCH (del)-[r:trata_do_mesmo_assunto]-(outra:Deliberação)
            RETURN type(r) AS tipo_relacao, outra.item_id_canonico AS relacionado_id,
                   outra.ato_emitido AS ato_emitido
        }
        RETURN item_id, tipo_relacao, relacionado_id AS item_id_canonico, ato_emitido
        """,
        item_ids=item_ids,
    )

    relacionadas_por_item: dict[str, list[dict]] = {item_id: [] for item_id in item_ids}
    for linha in linhas_relacionadas:
        relacionadas_por_item[linha["item_id"]].append(
            {
                "tipo_relacao": linha["tipo_relacao"],
                "item_id_canonico": linha["item_id_canonico"],
                "ato_emitido": linha["ato_emitido"],
            }
        )

    base_por_item = {linha["item_id"]: linha for linha in linhas_base}
    contextos = {}
    for item_id in item_ids:
        base = base_por_item.get(item_id, {})
        contextos[item_id] = {
            "centro": base.get("centro"),
            "departamento": base.get("departamento"),
            "data_reuniao": base.get("data_reuniao"),
            "tipo_desfecho": base.get("tipo_desfecho"),
            "resultado_votacao": base.get("resultado_votacao"),
            "ato_emitido": base.get("ato_emitido"),
            "encaminhamento": base.get("encaminhamento"),
            "deliberacoes_relacionadas": relacionadas_por_item[item_id],
        }
    return contextos
