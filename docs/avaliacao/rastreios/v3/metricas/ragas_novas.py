import asyncio
import json
import sys
from pathlib import Path

import httpx

from app.avaliacao.ragas_avaliacao import MODELO_JUIZ, EmbeddingsSerafim, JuizOllama, _pontuar, criar_metricas
from app.core.config import settings

PASTA = Path(sys.argv[1])
SAIDA = PASTA / "ragas_novas.jsonl"
TEMPO_LIMITE = 1800.0


def ler(caminho):
    return [json.loads(linha) for linha in caminho.open(encoding="utf-8")] if caminho.exists() else []


def main():
    referencias = {r["n"]: r["referencia"] for r in ler(PASTA / "referencias_40.jsonl")}
    perguntas = {p["id"]: p for p in ler(PASTA / "perguntas_novas.jsonl")}
    feitos = {r["id"] for r in ler(SAIDA)}
    juiz = JuizOllama(settings.ollama_base_url, timeout=TEMPO_LIMITE, guardar_saidas=True)
    metricas = criar_metricas(juiz, EmbeddingsSerafim())
    with asyncio.Runner() as executor:
        for g in ler(PASTA / "geracao_novas.jsonl"):
            p = perguntas[g["id"]]
            if g["id"] in feitos or not p["origem"] or g["abstencao"]:
                continue
            base = dict(user_input=p["pergunta"], retrieved_contexts=g["contextos"])
            chamadas = {
                "faithfulness": dict(base, response=g["texto"]),
                "answer_relevancy": dict(user_input=p["pergunta"], response=g["texto"]),
                "context_precision": dict(base, reference=referencias[p["origem"]]),
                "context_recall": dict(base, reference=referencias[p["origem"]]),
            }
            valores, erros = {}, {}
            for nome, kwargs in chamadas.items():
                try:
                    valor, erro = executor.run(_pontuar(metricas[nome], **kwargs))
                except httpx.TimeoutException:
                    valor, erro = None, f"tempo esgotado ({TEMPO_LIMITE:.0f} s por chamada)"
                valores[nome] = valor
                if erro:
                    erros[nome] = erro
            with SAIDA.open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps({"id": g["id"], "modelo_juiz": MODELO_JUIZ, **valores, "erros": erros},
                                         ensure_ascii=False) + "\n")
            print(g["id"], valores, erros or "", flush=True)


if __name__ == "__main__":
    main()
