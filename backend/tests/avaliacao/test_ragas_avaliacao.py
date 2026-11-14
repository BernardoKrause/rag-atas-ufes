import asyncio
import json
import math
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.avaliacao.ground_truth import PerguntaReferencia
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.avaliacao.ragas_avaliacao import (
    METRICAS,
    MODELO_JUIZ,
    MODELO_JUIZ_ANTHROPIC,
    JuizAnthropic,
    JuizOllama,
    _pontuar,
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
    assert mensagens.kwargs["model"] == MODELO_JUIZ_ANTHROPIC
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


def test_etapa_ragas_usa_um_unico_event_loop(tmp_path):
    ids = []

    class _MetricaLoop:
        async def ascore(self, **kwargs):
            ids.append(asyncio.get_running_loop())
            return SimpleNamespace(value=0.5)

    geracao = tmp_path / "geracao.jsonl"
    saida = tmp_path / "ragas.jsonl"
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="A"))
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="B"))
    juiz, _ = _juiz()
    metricas = {nome: _MetricaLoop() for nome in METRICAS}

    etapa_ragas([_pergunta("q1")], geracao, saida, metricas, juiz)

    assert len(ids) == 8
    assert all(loop is ids[0] for loop in ids)


def test_etapa_ragas_interrompe_em_falha_da_api_sem_gravar_o_par(tmp_path):
    geracao = tmp_path / "geracao.jsonl"
    saida = tmp_path / "ragas.jsonl"
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="A"))
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="B"))
    anexar_jsonl(saida, {"pergunta_id": "q1", "config": "A"})
    conexao = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    juiz, _ = _juiz()
    metricas = _metricas(faithfulness=_MetricaFalsa(erro=conexao))

    with pytest.raises(anthropic.APIConnectionError):
        etapa_ragas([_pergunta("q1")], geracao, saida, metricas, juiz)

    assert [(r["pergunta_id"], r["config"]) for r in ler_jsonl(saida)] == [("q1", "A")]


def _juiz_ollama(conteudo='{"valor": "oi"}', status=200, capturar=None, **kwargs):
    def responder(request):
        if capturar is not None:
            capturar.append(json.loads(request.content))
        corpo = {"message": {"content": conteudo}, "prompt_eval_count": 11, "eval_count": 5}
        return httpx.Response(status, json=corpo)

    return JuizOllama("http://ollama.falso", transport=httpx.MockTransport(responder), **kwargs)


def test_juiz_ollama_envia_schema_e_opcoes_e_soma_tokens():
    enviados = []
    juiz = _juiz_ollama(capturar=enviados)

    resultado = asyncio.run(juiz.agenerate("prompt", Saida))

    assert resultado == Saida(valor="oi")
    corpo = enviados[0]
    assert corpo["model"] == MODELO_JUIZ == "qwen2.5:14b"
    assert corpo["stream"] is False
    assert corpo["format"] == Saida.model_json_schema()
    assert corpo["options"] == {"temperature": 0, "num_ctx": 16384}
    assert corpo["messages"][0]["role"] == "system"
    assert "português" in corpo["messages"][0]["content"]
    assert corpo["messages"][1] == {"role": "user", "content": "prompt"}
    assert (juiz.tokens_entrada, juiz.tokens_saida) == (11, 5)


def test_juiz_ollama_guarda_saidas_quando_pedido():
    juiz = _juiz_ollama(guardar_saidas=True)

    asyncio.run(juiz.agenerate("prompt", Saida))

    assert juiz.saidas == [{"valor": "oi"}]


def test_juiz_ollama_generate_sincrono():
    assert _juiz_ollama().generate("prompt", Saida) == Saida(valor="oi")


def test_juiz_ollama_conteudo_invalido_levanta_validation_error():
    juiz = _juiz_ollama(conteudo='{"outro": 1}')

    with pytest.raises(ValidationError):
        asyncio.run(juiz.agenerate("prompt", Saida))


def test_juiz_ollama_conteudo_invalido_vira_erro_de_metrica():
    juiz = _juiz_ollama(conteudo="isto não é json")

    class Metrica:
        async def ascore(self, **kwargs):
            return await juiz.agenerate("p", Saida)

    valor, erro = asyncio.run(_pontuar(Metrica()))

    assert valor is None
    assert "ValidationError" in erro


def test_juiz_ollama_status_500_propaga_por_etapa_ragas_sem_gravar_o_par(tmp_path):
    geracao = tmp_path / "geracao.jsonl"
    saida = tmp_path / "ragas.jsonl"
    anexar_jsonl(geracao, _registro(pergunta_id="q1", config="A"))
    juiz = _juiz_ollama(status=500)

    class Metrica:
        async def ascore(self, **kwargs):
            return await juiz.agenerate("p", Saida)

    metricas = _metricas(faithfulness=Metrica())

    with pytest.raises(httpx.HTTPStatusError):
        etapa_ragas([_pergunta("q1")], geracao, saida, metricas, juiz)

    assert ler_jsonl(saida) == []


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
