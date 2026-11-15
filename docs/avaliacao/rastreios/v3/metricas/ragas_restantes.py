import asyncio
import csv
import json
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.avaliacao.ragas_avaliacao import MODELO_JUIZ, EmbeddingsSerafim, JuizOllama, _pontuar, criar_metricas
from app.core.config import settings
from app.ingestion.cleaner import anonimizar_texto

PASTA = Path(sys.argv[1])
GABARITO = Path(sys.argv[2])
CONFIG = sys.argv[3] if len(sys.argv) > 3 else "A"
GERACAO = PASTA / ("geracao_40.jsonl" if CONFIG == "A" else f"geracao_40_{CONFIG}.jsonl")
REFERENCIAS = PASTA / "referencias_40.jsonl"
SAIDA = PASTA / f"ragas_restantes_40_{CONFIG}.jsonl"
TEMPO_LIMITE = 1800.0
RESTANTES = ("answer_relevancy", "context_precision", "context_recall")


def ler(caminho):
    return [json.loads(linha) for linha in caminho.open(encoding="utf-8")] if caminho.exists() else []


def anexar(caminho, registro):
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def anonimizar_referencias():
    if REFERENCIAS.exists():
        return {r["n"]: r for r in ler(REFERENCIAS)}
    chave = settings.anonymization_secret_key.get_secret_value().encode()
    linhas = list(csv.DictReader(GABARITO.open(encoding="utf-8-sig"), delimiter=";"))
    sessao = sessionmaker(bind=create_engine(settings.database_url))()
    try:
        for linha in linhas:
            texto, _ = anonimizar_texto(linha["resposta_referencia"], chave, sessao)
            anexar(REFERENCIAS, {"n": linha["n"], "pergunta": linha["pergunta"], "referencia": texto})
    finally:
        sessao.rollback()
        sessao.close()
    return {r["n"]: r for r in ler(REFERENCIAS)}


def main():
    referencias = anonimizar_referencias()
    feitos = {r["n"] for r in ler(SAIDA)}
    juiz = JuizOllama(settings.ollama_base_url, timeout=TEMPO_LIMITE, guardar_saidas=True)
    metricas = criar_metricas(juiz, EmbeddingsSerafim())
    with asyncio.Runner() as executor:
        for registro in ler(GERACAO):
            n = registro["n"]
            if n in feitos:
                continue
            ref = referencias[n]
            chamadas = {}
            if not registro["abstencao"]:
                chamadas["answer_relevancy"] = dict(user_input=ref["pergunta"], response=registro["texto"])
            if registro["contextos"]:
                base = dict(user_input=ref["pergunta"], reference=ref["referencia"],
                            retrieved_contexts=registro["contextos"])
                chamadas["context_precision"] = base
                chamadas["context_recall"] = base
            valores, erros, segundos = dict.fromkeys(RESTANTES), {}, {}
            for nome, kwargs in chamadas.items():
                inicio = time.monotonic()
                try:
                    valor, erro = executor.run(_pontuar(metricas[nome], **kwargs))
                except httpx.TimeoutException:
                    valor, erro = None, f"tempo esgotado ({TEMPO_LIMITE:.0f} s por chamada)"
                valores[nome] = valor
                segundos[nome] = round(time.monotonic() - inicio)
                if erro:
                    erros[nome] = erro
            anexar(SAIDA, {"n": n, "config": CONFIG, "modelo_juiz": MODELO_JUIZ, **valores,
                           "erros": erros, "segundos": segundos})
            print(n, CONFIG, valores, erros or "", flush=True)


if __name__ == "__main__":
    main()
