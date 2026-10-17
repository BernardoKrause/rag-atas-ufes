from __future__ import annotations

import asyncio
import math
import typing as t
from pathlib import Path

import anthropic
from ragas.embeddings.base import BaseRagasEmbedding
from ragas.llms.base import InstructorBaseRagasLLM
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
    Faithfulness,
)

from app.avaliacao.ground_truth import PerguntaReferencia
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.ingestion.indexador import carregar_modelo, gerar_embedding, tokenizar_texto

MODELO_JUIZ = "claude-opus-5-5"
METRICAS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
SISTEMA_JUIZ = (
    "Você avalia respostas de um sistema de perguntas sobre atas de reuniões da UFES. "
    "Todo texto livre que você produzir (afirmações, perguntas, justificativas) deve estar em "
    "português do Brasil, no mesmo idioma do conteúdo avaliado."
)

T = t.TypeVar("T")


class JuizAnthropic(InstructorBaseRagasLLM):
    def __init__(
        self,
        cliente,
        modelo: str = MODELO_JUIZ,
        max_tokens: int = 16000,
        esforco: str = "medium",
        guardar_saidas: bool = False,
    ):
        self.cliente = cliente
        self.modelo = modelo
        self.max_tokens = max_tokens
        self.esforco = esforco
        self.guardar_saidas = guardar_saidas
        self.tokens_entrada = 0
        self.tokens_saida = 0
        self.saidas: list[dict] = []

    async def agenerate(self, prompt: str, response_model: type[T]) -> T:
        resposta = await self.cliente.messages.parse(
            model=self.modelo,
            max_tokens=self.max_tokens,
            system=SISTEMA_JUIZ,
            messages=[{"role": "user", "content": prompt}],
            output_format=response_model,
            output_config={"effort": self.esforco},
        )
        if resposta.stop_reason == "refusal":
            raise RuntimeError("o juiz recusou a requisição")
        self.tokens_entrada += resposta.usage.input_tokens
        self.tokens_saida += resposta.usage.output_tokens
        if self.guardar_saidas:
            self.saidas.append(resposta.parsed_output.model_dump())
        return resposta.parsed_output

    def generate(self, prompt: str, response_model: type[T]) -> T:
        return asyncio.run(self.agenerate(prompt, response_model))


class EmbeddingsSerafim(BaseRagasEmbedding):
    def __init__(self):
        super().__init__()
        self._tokenizer, self._modelo = carregar_modelo()

    def embed_text(self, text: str, **kwargs) -> list[float]:
        return gerar_embedding(self._tokenizer, self._modelo, tokenizar_texto(self._tokenizer, text))

    async def aembed_text(self, text: str, **kwargs) -> list[float]:
        return self.embed_text(text)


def criar_metricas(juiz: JuizAnthropic, embeddings: BaseRagasEmbedding) -> dict:
    return {
        "faithfulness": Faithfulness(llm=juiz),
        "answer_relevancy": AnswerRelevancy(llm=juiz, embeddings=embeddings),
        "context_precision": ContextPrecisionWithReference(llm=juiz),
        "context_recall": ContextRecall(llm=juiz),
    }


async def _pontuar(metrica, **kwargs) -> tuple[float | None, str | None]:
    try:
        resultado = await metrica.ascore(**kwargs)
    except anthropic.APIError:
        raise
    except Exception as erro:
        return None, f"{type(erro).__name__}: {erro}"
    valor = float(resultado.value)
    if math.isnan(valor):
        return None, "nan"
    return valor, None


async def avaliar_registro(metricas: dict, pergunta: PerguntaReferencia, registro: dict) -> dict:
    valores: dict[str, float | None] = dict.fromkeys(METRICAS)
    erros: dict[str, str] = {}
    contextos = registro["contextos"]
    chamadas = {}
    if not registro["abstencao"]:
        chamadas["faithfulness"] = dict(
            user_input=pergunta.pergunta, response=registro["texto"], retrieved_contexts=contextos
        )
        chamadas["answer_relevancy"] = dict(user_input=pergunta.pergunta, response=registro["texto"])
    if contextos:
        com_referencia = dict(
            user_input=pergunta.pergunta, reference=pergunta.resposta_referencia,
            retrieved_contexts=contextos,
        )
        chamadas["context_precision"] = com_referencia
        chamadas["context_recall"] = com_referencia
    for nome, kwargs in chamadas.items():
        valor, erro = await _pontuar(metricas[nome], **kwargs)
        valores[nome] = valor
        if erro:
            erros[nome] = erro
    return {**valores, "erros": erros}


def etapa_ragas(
    perguntas: list[PerguntaReferencia],
    geracao: Path,
    saida: Path,
    metricas: dict,
    juiz: JuizAnthropic,
) -> int:
    por_id = {pergunta.id: pergunta for pergunta in perguntas}
    feitos = {(r["pergunta_id"], r["config"]) for r in ler_jsonl(saida)}
    total = 0
    with asyncio.Runner() as executor:
        for registro in ler_jsonl(geracao):
            pergunta = por_id.get(registro["pergunta_id"])
            chave = (registro["pergunta_id"], registro["config"])
            if (
                pergunta is None
                or pergunta.categoria == "sem_evidencia"
                or registro["erro"]
                or chave in feitos
            ):
                continue
            antes = (juiz.tokens_entrada, juiz.tokens_saida)
            resultado = executor.run(avaliar_registro(metricas, pergunta, registro))
            anexar_jsonl(saida, {
                "pergunta_id": registro["pergunta_id"],
                "config": registro["config"],
                **resultado,
                "tokens_juiz_entrada": juiz.tokens_entrada - antes[0],
                "tokens_juiz_saida": juiz.tokens_saida - antes[1],
            })
            total += 1
    return total
