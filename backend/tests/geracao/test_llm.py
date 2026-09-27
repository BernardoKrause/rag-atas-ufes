import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.geracao.llm import ClienteAnthropic, ClienteOllama, criar_cliente_llm
from app.geracao.tipos import ErroGeracao, SaidaLLM

MODELO_ANTHROPIC_TESTE = "claude-opus-5"


def _ollama_falso(resposta_json=None, status=200, capturar=None):
    def responder(request):
        if capturar is not None:
            capturar.append(json.loads(request.content))
        return httpx.Response(status, json=resposta_json or {})
    return ClienteOllama(
        "http://ollama.falso", "modelo-x", timeout=5, max_tokens=64,
        transport=httpx.MockTransport(responder),
    )


def test_ollama_envia_sistema_usuario_e_temperatura_zero():
    enviados = []
    cliente = _ollama_falso(
        {"message": {"content": "ok [1]"}, "done_reason": "stop"}, capturar=enviados
    )

    saida = cliente.gerar("regras", "pergunta")

    assert saida == SaidaLLM(texto="ok [1]", truncada=False)
    corpo = enviados[0]
    assert corpo["model"] == "modelo-x"
    assert corpo["stream"] is False
    assert corpo["messages"] == [
        {"role": "system", "content": "regras"},
        {"role": "user", "content": "pergunta"},
    ]
    assert corpo["options"] == {"temperature": 0, "num_predict": 64}


def test_ollama_marca_truncada_quando_done_reason_length():
    cliente = _ollama_falso({"message": {"content": "cortad"}, "done_reason": "length"})
    assert cliente.gerar("s", "u").truncada is True


def test_ollama_erro_http_vira_erro_geracao():
    cliente = _ollama_falso({"error": "model not found"}, status=404)
    with pytest.raises(ErroGeracao):
        cliente.gerar("s", "u")


def test_ollama_porta_fechada_vira_erro_geracao():
    cliente = ClienteOllama("http://127.0.0.1:1", "modelo-x", timeout=2, max_tokens=16)
    with pytest.raises(ErroGeracao):
        cliente.gerar("s", "u")


def test_criar_cliente_llm_escolhe_por_provedor():
    ollama = settings.model_copy(update={"llm_provedor": "ollama"})
    anthropic_cfg = settings.model_copy(
        update={
            "llm_provedor": "anthropic",
            "llm_modelo": MODELO_ANTHROPIC_TESTE,
            "anthropic_api_key": SecretStr("chave-de-teste"),
        }
    )
    assert isinstance(criar_cliente_llm(ollama), ClienteOllama)
    assert isinstance(criar_cliente_llm(anthropic_cfg), ClienteAnthropic)


def test_criar_cliente_llm_rejeita_provedor_desconhecido():
    with pytest.raises(ValueError):
        criar_cliente_llm(settings.model_copy(update={"llm_provedor": "openai"}))


def _ollama_tem_modelo(modelo):
    try:
        tags = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).json()
    except httpx.HTTPError:
        return False
    return any(m["name"] == modelo for m in tags.get("models", []))


@pytest.mark.skipif(
    not _ollama_tem_modelo(settings.llm_modelo), reason="Ollama indisponível ou modelo ausente"
)
def test_ollama_real_responde_texto():
    cliente = ClienteOllama(
        settings.ollama_base_url, settings.llm_modelo, timeout=settings.llm_timeout, max_tokens=32
    )
    saida = cliente.gerar("Responda com uma palavra.", "Diga olá.")
    assert saida.texto.strip()


def _tem_chave_anthropic():
    chave = settings.anthropic_api_key
    return chave is not None and chave.get_secret_value() != ""


@pytest.mark.skipif(not _tem_chave_anthropic(), reason="ANTHROPIC_API_KEY ausente")
def test_anthropic_real_responde_texto():
    cliente = ClienteAnthropic(
        MODELO_ANTHROPIC_TESTE, timeout=60, max_tokens=1024,
        api_key=settings.anthropic_api_key.get_secret_value(),
    )
    saida = cliente.gerar("Responda com uma palavra.", "Diga olá.")
    assert saida.texto.strip()
