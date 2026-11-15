import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
from ragas.metrics.collections import Faithfulness

from app.avaliacao.etapas import CONFIGURACOES, _registro_geracao
from app.avaliacao.executar import MODELO_GERADOR, _clientes
from app.avaliacao.itens import mapa_item_logico
from app.avaliacao.ragas_avaliacao import MODELO_JUIZ, JuizOllama, _pontuar
from app.core.config import settings
from app.geracao.llm import criar_cliente_llm
from app.geracao.respondedor import responder_detalhado

PASTA = Path(sys.argv[1])
ETAPA = sys.argv[2]
GERACAO = PASTA / "geracao_40_B.jsonl"
FIDELIDADE = PASTA / "fidelidade_40_B.jsonl"
TEMPO_LIMITE = 1800.0


def ler(caminho):
    return [json.loads(linha) for linha in caminho.open(encoding="utf-8")] if caminho.exists() else []


def anexar(caminho, registro):
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def perguntas():
    return {r["n"]: r["pergunta"] for r in ler(PASTA / "referencias_40.jsonl")}


def gerar():
    feitos = {r["n"] for r in ler(GERACAO)}
    Sessao, qdrant, driver = _clientes()
    cliente_llm = criar_cliente_llm()
    try:
        with Sessao() as sessao:
            mapa = mapa_item_logico(sessao)
            for n, pergunta in perguntas().items():
                if n in feitos:
                    continue
                detalhada = responder_detalhado(
                    pergunta, sessao, qdrant, driver, cliente_llm, camadas=CONFIGURACOES["B"]
                )
                registro = _registro_geracao(n, "B", MODELO_GERADOR, detalhada, mapa)
                registro["n"] = n
                anexar(GERACAO, registro)
                print(n, "B gerada", flush=True)
    finally:
        driver.close()
        qdrant.close()


def fidelidade():
    textos = perguntas()
    feitos = {r["n"] for r in ler(FIDELIDADE)}
    juiz = JuizOllama(settings.ollama_base_url, timeout=TEMPO_LIMITE, guardar_saidas=True)
    metrica = Faithfulness(llm=juiz)
    with asyncio.Runner() as executor:
        for registro in ler(GERACAO):
            if registro["n"] in feitos or registro["abstencao"]:
                continue
            antes = len(juiz.saidas)
            inicio = time.monotonic()
            try:
                valor, erro = executor.run(_pontuar(
                    metrica, user_input=textos[registro["n"]], response=registro["texto"],
                    retrieved_contexts=registro["contextos"],
                ))
            except httpx.TimeoutException:
                valor, erro = None, f"tempo esgotado ({TEMPO_LIMITE:.0f} s por chamada)"
            anexar(FIDELIDADE, {
                "n": registro["n"], "config": "B", "modelo_juiz": MODELO_JUIZ, "faithfulness": valor,
                "erro": erro, "segundos": round(time.monotonic() - inicio),
                "saidas_juiz": juiz.saidas[antes:],
            })
            print(registro["n"], "B", valor, erro or "", flush=True)


if __name__ == "__main__":
    {"gerar": gerar, "fidelidade": fidelidade}[ETAPA]()
