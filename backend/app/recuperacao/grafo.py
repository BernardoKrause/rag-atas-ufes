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
