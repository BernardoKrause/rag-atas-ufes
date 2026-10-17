import asyncio
import math
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.avaliacao.ground_truth import PerguntaReferencia
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.avaliacao.ragas_avaliacao import (
    MODELO_JUIZ,
    JuizAnthropic,
    avaliar_registro,
    etapa_ragas,
)
from app.core.config import settings


class Saida(BaseModel):
    valor: str


class _MensagensFalsas:
    def __init__(self, stop_reason="end_turn"):
        self.kwargs = None
        self.stop_reason = stop_reason

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            parsed_output=Saida(valor="oi"),
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
        )


def _juiz(stop_reason="end_turn", **kwargs):
    mensagens = _MensagensFalsas(stop_reason)
    return JuizAnthropic(SimpleNamespace(messages=mensagens), **kwargs), mensagens


def test_juiz_usa_structured_output_sem_sampling_nem_tool_choice():
    juiz, mensagens = _juiz()

    resultado = asyncio.run(juiz.agenerate("prompt", Saida))

    assert resultado == Saida(valor="oi")
    assert mensagens.kwargs["model"] == MODELO_JUIZ
    assert mensagens.kwargs["output_format"] is Saida
    assert mensagens.kwargs["output_config"] == {"effort": "medium"}
    assert "português" in mensagens.kwargs["system"]
    for proibido in ("temperature", "top_p", "tool_choice", "fallbacks"):
        assert proibido not in mensagens.kwargs
    assert (juiz.tokens_entrada, juiz.tokens_saida) == (7, 3)


def test_juiz_guarda_saidas_quando_pedido():
    juiz, _ = _juiz(guardar_saidas=True)

    asyncio.run(juiz.agenerate("prompt", Saida))

    assert juiz.saidas == [{"valor": "oi"}]


def test_juiz_recusa_vira_erro():
    juiz, _ = _juiz(stop_reason="refusal")

    with pytest.raises(RuntimeError):
        asyncio.run(juiz.agenerate("prompt", Saida))


def test_juiz_generate_sincrono():
    juiz, _ = _juiz()

    assert juiz.generate("prompt", Saida) == Saida(valor="oi")


class _MetricaFalsa:
    def __init__(self, valor=None, erro=None):
        self.valor = valor
        self.erro = erro
        self.kwargs = None

    async def ascore(self, **kwargs):
        self.kwargs = kwargs
        if self.erro:
            raise self.erro
        return SimpleNamespace(value=self.valor)


def _pergunta(id_="q1", categoria="intra_exata"):
    return PerguntaReferencia(
        id=id_, categoria=categoria, origem="autor", pergunta="pergunta?",
        resposta_referencia="referência", itens_relevantes=("i1",), trechos_evidencia=("t",),
        sequencia_cronologica=(), tipo_dificuldade="", observacao="",
    )


def _registro(**campos):
    base = {
        "pergunta_id": "q1", "config": "A", "texto": "resposta [1]", "abstencao": False,
        "contextos": ["ctx 1", "ctx 2"], "erro": None,
    }
    base.update(campos)
    return base


def _metricas(**sobrescritas):
    metricas = {
        "faithfulness": _MetricaFalsa(0.9),
        "answer_relevancy": _MetricaFalsa(0.8),
        "context_precision": _MetricaFalsa(0.7),
        "context_recall": _MetricaFalsa(0.6),
    }
    metricas.update(sobrescritas)
    return metricas


def test_avaliar_registro_passa_os_campos_certos_a_cada_metrica():
    metricas = _metricas()

    resultado = asyncio.run(avaliar_registro(metricas, _pergunta(), _registro()))

    assert resultado["faithfulness"] == 0.9
    assert resultado["context_recall"] == 0.6
    assert metricas["faithfulness"].kwargs == {
        "user_input": "pergunta?", "response": "resposta [1]", "retrieved_contexts": ["ctx 1", "ctx 2"],
    }
    assert metricas["answer_relevancy"].kwargs == {"user_input": "pergunta?", "response": "resposta [1]"}
    assert metricas["context_precision"].kwargs == {
        "user_input": "pergunta?", "reference": "referência", "retrieved_contexts": ["ctx 1", "ctx 2"],
    }
    assert metricas["context_recall"].kwargs == metricas["context_precision"].kwargs


def test_abstencao_so_avalia_contexto():
    metricas = _metricas()

    resultado = asyncio.run(avaliar_registro(metricas, _pergunta(), _registro(abstencao=True)))

    assert resultado["faithfulness"] is None
    assert resultado["answer_relevancy"] is None
    assert metricas["faithfulness"].kwargs is None
    assert resultado["context_precision"] == 0.7


def test_sem_contextos_nao_avalia_contexto():
    resultado = asyncio.run(
        avaliar_registro(_metricas(), _pergunta(), _registro(abstencao=True, contextos=[]))
    )

    assert resultado["context_precision"] is None
    assert resultado["context_recall"] is None


def test_metrica_com_erro_ou_nan_vira_none_com_mensagem():
    metricas = _metricas(
        faithfulness=_MetricaFalsa(erro=ValueError("quebrou")),
        context_recall=_MetricaFalsa(math.nan),
    )

    resultado = asyncio.run(avaliar_registro(metricas, _pergunta(), _registro()))

    assert resultado["faithfulness"] is None
    assert "quebrou" in resultado["erros"]["faithfulness"]
    assert resultado["context_recall"] is None
    assert resultado["erros"]["context_recall"] == "nan"


def test_etapa_ragas_retoma_e_pula_sem_evidencia_e_erros(tmp_path):
    geracao = tmp_path / "geracao.jsonl"
    saida = tmp_path / "ragas.jsonl"
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="A"))
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="B"))
    anexar_jsonl(geracao, _registro(pergunta_id="q2", config="A"))
    anexar_jsonl(geracao, _registro(pergunta_id="q3", config="A", erro="recusou"))
    anexar_jsonl(saida, {"pergunta_id": "q1", "config": "A"})
    perguntas = [_pergunta("q1"), _pergunta("q2", "sem_evidencia"), _pergunta("q3")]
    juiz, _ = _juiz()

    total = etapa_ragas(perguntas, geracao, saida, _metricas(), juiz)

    registros = ler_jsonl(saida)
    assert total == 1
    assert [(r["pergunta_id"], r["config"]) for r in registros] == [("q1", "A"), ("q1", "B")]
    assert "tokens_juiz_entrada" in registros[1]


def _tem_chave():
    chave = settings.anthropic_api_key
    return chave is not None and chave.get_secret_value().strip() != ""


@pytest.mark.skipif(not _tem_chave(), reason="ANTHROPIC_API_KEY ausente")
def test_fumaca_faithfulness_real():
    from anthropic import AsyncAnthropic

    from app.avaliacao.ragas_avaliacao import Faithfulness

    juiz = JuizAnthropic(
        AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()), esforco="low"
    )
    resultado = asyncio.run(Faithfulness(llm=juiz).ascore(
        user_input="O que o departamento decidiu sobre o afastamento?",
        response="O departamento aprovou o afastamento por unanimidade.",
        retrieved_contexts=["Item 1. Afastamento para doutorado. Aprovado por unanimidade."],
    ))

    assert 0.0 <= float(resultado.value) <= 1.0
    assert juiz.tokens_entrada > 0
