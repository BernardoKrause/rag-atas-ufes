from __future__ import annotations

import math


def agrupar_fragmentos(ranking: list[str], mapa_logico: dict[str, str]) -> list[str]:
    agrupado = []
    for item_id in ranking:
        logico = mapa_logico.get(item_id, item_id)
        if logico not in agrupado:
            agrupado.append(logico)
    return agrupado


def _acertos(ranking: list[str], relevantes: set[str], k: int) -> int:
    return sum(1 for item_id in ranking[:k] if item_id in relevantes)


def precisao_em_k(ranking: list[str], relevantes: set[str], k: int = 5) -> float:
    return _acertos(ranking, relevantes, k) / k


def revocacao_em_k(ranking: list[str], relevantes: set[str], k: int = 5) -> float:
    if not relevantes:
        raise ValueError("revocação indefinida sem itens relevantes")
    return _acertos(ranking, relevantes, k) / len(relevantes)


def rank_reciproco(ranking: list[str], relevantes: set[str], k: int = 5) -> float:
    for posicao, item_id in enumerate(ranking[:k], start=1):
        if item_id in relevantes:
            return 1 / posicao
    return 0.0


def ndcg_em_k(ranking: list[str], relevantes: set[str], k: int = 5) -> float:
    if not relevantes:
        raise ValueError("nDCG indefinido sem itens relevantes")
    dcg = sum(
        1 / math.log2(posicao + 2)
        for posicao, item_id in enumerate(ranking[:k])
        if item_id in relevantes
    )
    idcg = sum(1 / math.log2(posicao + 2) for posicao in range(min(len(relevantes), k)))
    return dcg / idcg


def cobertura_sequencia(encontrados: set[str], sequencia: tuple[str, ...]) -> float:
    return sum(1 for item_id in sequencia if item_id in encontrados) / len(sequencia)
