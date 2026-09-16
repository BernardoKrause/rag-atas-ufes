from __future__ import annotations

from qdrant_client import QdrantClient

from app.ingestion.indexador import COLLECTION, carregar_modelo, gerar_embedding, tokenizar_texto
from app.recuperacao.tipos import LIMITE_PADRAO, Hit


def buscar_vetorial(pergunta: str, cliente: QdrantClient, limite_janelas: int = LIMITE_PADRAO) -> list[Hit]:
    tokenizer, modelo = carregar_modelo()
    embedding = gerar_embedding(tokenizer, modelo, tokenizar_texto(tokenizer, pergunta))

    resultado = cliente.query_points(collection_name=COLLECTION, query=embedding, limit=limite_janelas)

    melhor_score_por_item: dict[str, float] = {}
    for ponto in resultado.points:
        item_id = ponto.payload["item_id_canonico"]
        if item_id not in melhor_score_por_item or ponto.score > melhor_score_por_item[item_id]:
            melhor_score_por_item[item_id] = ponto.score

    ordenados = sorted(melhor_score_por_item.items(), key=lambda par: par[1], reverse=True)
    return [
        Hit(item_id_canonico=item_id, rank=indice + 1, score=score)
        for indice, (item_id, score) in enumerate(ordenados)
    ]
