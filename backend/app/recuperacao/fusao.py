from __future__ import annotations

from app.recuperacao.tipos import Hit

# Cormack, Clarke & Buttcher (2009), SIGIR — constante padrao avaliada pelos autores.
RRF_K = 60
PROFUNDIDADE_FUSAO = 10


def ancorar(hits_lexico: list[Hit], hits_vetorial: list[Hit], top_n: int = 10) -> list[Hit]:
    candidatos: dict[str, Hit] = {}
    for hit in [*hits_lexico[:top_n], *hits_vetorial[:top_n]]:
        existente = candidatos.get(hit.item_id_canonico)
        if existente is None or hit.rank < existente.rank:
            candidatos[hit.item_id_canonico] = hit
    return sorted(candidatos.values(), key=lambda hit: hit.rank)


def pontuar_rrf(
    hits_lexico: list[Hit],
    hits_vetorial: list[Hit],
    hits_grafo: list[Hit],
    rrf_k: int = RRF_K,
    profundidade: int = PROFUNDIDADE_FUSAO,
) -> list[dict]:
    pontuados: dict[str, dict] = {}
    for nome, lista in (("lexico", hits_lexico), ("vetorial", hits_vetorial), ("grafo", hits_grafo)):
        for hit in lista[:profundidade]:
            linha = pontuados.setdefault(
                hit.item_id_canonico,
                {"item_id_canonico": hit.item_id_canonico, "pontuacao": 0.0, "posicoes": {}},
            )
            linha["pontuacao"] += 1.0 / (rrf_k + hit.rank)
            linha["posicoes"][nome] = hit.rank
    return sorted(pontuados.values(), key=lambda linha: linha["pontuacao"], reverse=True)


def fundir_rrf(
    hits_lexico: list[Hit],
    hits_vetorial: list[Hit],
    hits_grafo: list[Hit],
    k: int,
    rrf_k: int = RRF_K,
    profundidade: int = PROFUNDIDADE_FUSAO,
) -> list[str]:
    pontuados = pontuar_rrf(hits_lexico, hits_vetorial, hits_grafo, rrf_k, profundidade)
    return [linha["item_id_canonico"] for linha in pontuados[:k]]
