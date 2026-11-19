from __future__ import annotations

import math
from statistics import mean

from app.avaliacao.metricas import agrupar_fragmentos


def relevantes_da_referencia(referencia: dict, mapa_logico: dict[str, str]) -> tuple[set[str], list[dict]]:
    relevantes, sem_identificador = set(), []
    for evidencia in referencia["evidencias"]:
        item_id = evidencia.get("identificador_item")
        if item_id:
            relevantes.add(mapa_logico.get(item_id, item_id))
        else:
            sem_identificador.append(evidencia)
    return relevantes, sem_identificador


def origem_por_item(fusao: list[dict], mapa_logico: dict[str, str]) -> dict[str, dict]:
    origem: dict[str, dict] = {}
    for linha in fusao:
        logico = mapa_logico.get(linha["item_id_canonico"], linha["item_id_canonico"])
        atual = origem.setdefault(logico, {"pontuacao_rrf": linha["pontuacao"], "posicoes": {}, "fragmentos": []})
        atual["fragmentos"].append(linha["item_id_canonico"])
        for busca, posicao in linha["posicoes"].items():
            atual["posicoes"].setdefault(busca, posicao)
    return origem


def avaliar_ranking(ranking: list[str], relevantes: set[str], k: int) -> dict:
    topo = ranking[:k]
    acertos = [item_id for item_id in topo if item_id in relevantes]
    tp, fp = len(acertos), len(topo) - len(acertos)
    fn = len(relevantes - set(topo))
    primeira = next((posicao for posicao, item_id in enumerate(topo, start=1) if item_id in relevantes), None)
    dcg = sum(1 / math.log2(posicao + 1) for posicao, item_id in enumerate(topo, start=1) if item_id in relevantes)
    idcg = sum(1 / math.log2(posicao + 1) for posicao in range(1, min(len(relevantes), k) + 1))
    return {
        "k": k,
        "itens_na_lista": len(topo),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "relevantes": len(relevantes),
        "precisao": tp / k,
        "revocacao": tp / len(relevantes) if relevantes else None,
        "revocacao_maxima": min(k, len(relevantes)) / len(relevantes) if relevantes else None,
        "primeira_posicao_relevante": primeira,
        "rr": 1 / primeira if primeira else 0.0,
        "dcg": dcg,
        "idcg": idcg,
        "ndcg": dcg / idcg if idcg else None,
        "faltantes": sorted(relevantes - set(topo)),
    }


def linhas_do_ranking(ranking: list[str], relevantes: set[str], origem: dict[str, dict]) -> list[dict]:
    return [
        {
            "posicao": posicao,
            "item_id": item_id,
            "relevante": item_id in relevantes,
            "fragmentos": origem.get(item_id, {}).get("fragmentos", [item_id]),
            "posicoes_nas_buscas": origem.get(item_id, {}).get("posicoes", {}),
            "pontuacao_rrf": origem.get(item_id, {}).get("pontuacao_rrf"),
        }
        for posicao, item_id in enumerate(ranking, start=1)
    ]


def ranking_logico(ids: list[str], mapa_logico: dict[str, str]) -> list[str]:
    return agrupar_fragmentos(ids, mapa_logico)


def agregar(avaliacoes: list[dict]) -> dict:
    com_relevantes = [a for a in avaliacoes if a["relevantes"]]
    if not com_relevantes:
        return {"perguntas": 0}
    soma_tp = sum(a["tp"] for a in com_relevantes)
    return {
        "perguntas": len(com_relevantes),
        "precisao_media": mean(a["precisao"] for a in com_relevantes),
        "revocacao_media": mean(a["revocacao"] for a in com_relevantes),
        "mrr": mean(a["rr"] for a in com_relevantes),
        "ndcg_medio": mean(a["ndcg"] for a in com_relevantes),
        "revocacao_maxima_media": mean(a["revocacao_maxima"] for a in com_relevantes),
        "tp_total": soma_tp,
        "relevantes_total": sum(a["relevantes"] for a in com_relevantes),
        "posicoes_total": sum(a["k"] for a in com_relevantes),
        "revocacao_micro": soma_tp / sum(a["relevantes"] for a in com_relevantes),
        "precisao_micro": soma_tp / sum(a["k"] for a in com_relevantes),
    }
