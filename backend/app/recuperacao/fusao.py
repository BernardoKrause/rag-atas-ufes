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


def fundir_rrf(
    hits_lexico: list[Hit],
    hits_vetorial: list[Hit],
    hits_grafo: list[Hit],
    k: int,
    rrf_k: int = RRF_K,
    profundidade: int = PROFUNDIDADE_FUSAO,
) -> list[str]:
    pontuacao: dict[str, float] = {}
    for lista in (hits_lexico, hits_vetorial, hits_grafo):
        for hit in lista[:profundidade]:
            pontuacao[hit.item_id_canonico] = pontuacao.get(hit.item_id_canonico, 0.0) + 1.0 / (rrf_k + hit.rank)

    ordenados = sorted(pontuacao.items(), key=lambda par: par[1], reverse=True)
    return [item_id for item_id, _ in ordenados[:k]]
