import asyncio
import json
import time
import re
import sys
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
PRERODADA = Path(sys.argv[2])
GERACAO = PASTA / "geracao_40.jsonl"
FIDELIDADE = PASTA / "fidelidade_40.jsonl"
TEMPO_LIMITE = 1800.0
PROCESSO = re.compile(r"PROCESSO_\d+|\d{5}\.\d{6}/\d{4}-\d{2}")


def ler(caminho):
    return [json.loads(l) for l in caminho.open(encoding="utf-8")] if caminho.exists() else []


def anexar(caminho, registro):
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def normalizar(texto):
    return PROCESSO.sub("<PROCESSO>", texto or "")


def gerar(prerodada):
    feitos = {r["n"] for r in ler(GERACAO)}
    Sessao, qdrant, driver = _clientes()
    cliente_llm = criar_cliente_llm()
    try:
        with Sessao() as sessao:
            mapa = mapa_item_logico(sessao)
            for p in prerodada:
                if p["n"] in feitos:
                    continue
                detalhada = responder_detalhado(
                    p["pergunta"], sessao, qdrant, driver, cliente_llm, camadas=CONFIGURACOES["A"]
                )
                registro = _registro_geracao(p["n"], "A", MODELO_GERADOR, detalhada, mapa)
                registro["n"] = p["n"]
                registro["igual_prerodada"] = normalizar(registro["texto"]) == normalizar(p["resposta"]["texto"])
                anexar(GERACAO, registro)
                print(p["n"], "igual" if registro["igual_prerodada"] else "DIFERENTE", flush=True)
    finally:
        driver.close()
        qdrant.close()


def avaliar(prerodada):
    perguntas = {p["n"]: p["pergunta"] for p in prerodada}
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
                valor, erro = executor.run(
                    _pontuar(
                        metrica,
                        user_input=perguntas[registro["n"]],
                        response=registro["texto"],
                        retrieved_contexts=registro["contextos"],
                    )
                )
            except httpx.TimeoutException:
                valor, erro = None, f"tempo esgotado ({TEMPO_LIMITE:.0f} s por chamada)"
            anexar(FIDELIDADE, {
                "n": registro["n"], "modelo_juiz": MODELO_JUIZ, "faithfulness": valor, "erro": erro,
                "segundos": round(time.monotonic() - inicio), "saidas_juiz": juiz.saidas[antes:],
            })
            print(registro["n"], valor, erro or "", flush=True)


def main():
    prerodada = ler(PRERODADA)
    gerar(prerodada)
    avaliar(prerodada)


if __name__ == "__main__":
    main()
