import json
import sys
from pathlib import Path

from app.avaliacao.etapas import CONFIGURACOES
from app.avaliacao.executar import _clientes
from app.avaliacao.itens import mapa_item_logico
from app.avaliacao.metricas import (
    agrupar_fragmentos,
    ndcg_em_k,
    precisao_em_k,
    rank_reciproco,
    revocacao_em_k,
)
from app.recuperacao.orquestrador import recuperar

PASTA = Path(sys.argv[1])
PERGUNTAS = Path(sys.argv[2])
K = 5


def main():
    gabarito = [json.loads(l) for l in (PASTA / "gabarito_itens.jsonl").open(encoding="utf-8")]
    perguntas = {p["n"]: p["pergunta"] for p in map(json.loads, PERGUNTAS.open(encoding="utf-8"))}
    Sessao, qdrant, driver = _clientes()
    saida = []
    try:
        with Sessao() as sessao:
            mapa = mapa_item_logico(sessao)
            for g in gabarito:
                relevantes = {mapa.get(i, i) for r in g["registros"] for i in r["itens"]}
                for config, camadas in CONFIGURACOES.items():
                    evidencias = recuperar(perguntas[g["n"]], sessao, qdrant, driver, k=K, camadas=camadas)
                    ranking = [e.item_id_canonico for e in evidencias]
                    logico = agrupar_fragmentos(ranking, mapa)
                    saida.append({
                        "n": g["n"], "situacao": g["situacao"], "config": config,
                        "relevantes": sorted(relevantes), "ranking": ranking, "ranking_logico": logico,
                        "acertos": [i for i in logico[:K] if i in relevantes],
                        "p5": precisao_em_k(logico, relevantes, K),
                        "r5": revocacao_em_k(logico, relevantes, K),
                        "mrr": rank_reciproco(logico, relevantes, K),
                        "ndcg5": ndcg_em_k(logico, relevantes, K),
                    })
    finally:
        driver.close()
        qdrant.close()
    (PASTA / "recuperacao_40.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in saida) + "\n", encoding="utf-8"
    )
    print(f"{len(saida)} registros")


if __name__ == "__main__":
    main()
