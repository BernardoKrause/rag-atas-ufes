import csv
import json
import statistics
import sys
from pathlib import Path

PASTA = Path(sys.argv[1])
TESTE = Path(sys.argv[2])
SAIDA = Path(sys.argv[3])


def ler(caminho):
    return [json.loads(l) for l in caminho.open(encoding="utf-8")] if caminho.exists() else []


def num(valor):
    return "" if valor is None else f"{valor:.3f}".replace(".", ",")


def main():
    recuperacao = [r for r in ler(PASTA / "recuperacao_40.jsonl") if r["config"] == "A"]
    fidelidade = {r["n"]: r for r in ler(PASTA / "fidelidade_40.jsonl")}
    geracao = {r["n"]: r for r in ler(PASTA / "geracao_40.jsonl")}
    linhas = list(csv.DictReader(TESTE.open(encoding="utf-8", newline=""), delimiter=";"))
    classe = {l["n"]: l["classe"] for l in linhas if l.get("versao_sistema") == "v3"}
    campos = [
        "n", "situacao", "classe", "itens_relevantes", "teto_r5", "p5", "r5", "mrr", "ndcg5",
        "faithfulness", "acertos", "ranking_logico", "relevantes", "resposta_igual_prerodada",
    ]
    with SAIDA.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for r in recuperacao:
            f = fidelidade.get(r["n"], {})
            escritor.writerow({
                "n": r["n"], "situacao": r["situacao"], "classe": classe.get(r["n"], ""),
                "itens_relevantes": len(r["relevantes"]),
                "teto_r5": num(min(1, 5 / len(r["relevantes"]))),
                "p5": num(r["p5"]), "r5": num(r["r5"]), "mrr": num(r["mrr"]), "ndcg5": num(r["ndcg5"]),
                "faithfulness": num(f.get("faithfulness")),
                "acertos": " | ".join(r["acertos"]), "ranking_logico": " | ".join(r["ranking_logico"]),
                "relevantes": " | ".join(r["relevantes"]),
                "resposta_igual_prerodada": {True: "sim", False: "nao"}.get(
                    geracao.get(r["n"], {}).get("igual_prerodada"), ""
                ),
            })
    valores = [f["faithfulness"] for f in fidelidade.values() if f.get("faithfulness") is not None]
    print(len(recuperacao), "linhas;", len(valores), "com faithfulness",
          f"média {statistics.mean(valores):.3f}" if valores else "")


if __name__ == "__main__":
    main()
