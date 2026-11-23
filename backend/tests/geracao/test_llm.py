import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.geracao.llm import (
    ClienteAnthropic,
    ClienteOllama,
    criar_cliente_llm,
    modelos_instalados,
    modelos_permitidos,
    parametros_geracao,
)
from app.geracao.tipos import ErroGeracao, SaidaLLM

MODELO_ANTHROPIC_TESTE = "claude-opus-5"


def _ollama_falso(resposta_json=None, status=200, capturar=None):
    def responder(request):
        if capturar is not None:
            capturar.append(json.loads(request.content))
        return httpx.Response(status, json=resposta_json or {})
    return ClienteOllama(
        "http://ollama.falso", "modelo-x", timeout=5, max_tokens=64, num_ctx=8192,
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
    assert corpo["options"] == {"temperature": 0, "num_predict": 64, "num_ctx": 8192}


def test_ollama_envia_esquema_como_format():
    enviados = []
    cliente = _ollama_falso({"message": {"content": "{}"}, "done_reason": "stop"}, capturar=enviados)
    esquema = {"type": "object", "properties": {"eventos": {"type": "array"}}}

    cliente.gerar("s", "u", esquema=esquema)

    assert enviados[0]["format"] == esquema


def test_ollama_sem_esquema_nao_envia_format():
    enviados = []
    cliente = _ollama_falso({"message": {"content": "ok"}, "done_reason": "stop"}, capturar=enviados)

    cliente.gerar("s", "u")

    assert "format" not in enviados[0]


def test_ollama_registra_tokens_de_entrada_e_saida():
    cliente = _ollama_falso(
        {"message": {"content": "ok"}, "done_reason": "stop",
         "prompt_eval_count": 120, "eval_count": 30}
    )

    saida = cliente.gerar("s", "u")

    assert (saida.tokens_entrada, saida.tokens_saida) == (120, 30)


def test_ollama_marca_truncada_quando_done_reason_length():
    cliente = _ollama_falso({"message": {"content": "cortad"}, "done_reason": "length"})
    assert cliente.gerar("s", "u").truncada is True


def test_ollama_erro_http_vira_erro_geracao():
    cliente = _ollama_falso({"error": "model not found"}, status=404)
    with pytest.raises(ErroGeracao):
        cliente.gerar("s", "u")


def test_ollama_resposta_sem_message_vira_erro_geracao():
    cliente = _ollama_falso({"done_reason": "stop"})
    with pytest.raises(ErroGeracao):
        cliente.gerar("s", "u")


def test_ollama_resposta_nao_json_vira_erro_geracao():
    cliente = ClienteOllama(
        "http://ollama.falso", "modelo-x", timeout=5, max_tokens=64, num_ctx=8192,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="não é json")),
    )
    with pytest.raises(ErroGeracao):
        cliente.gerar("s", "u")


def test_ollama_porta_fechada_vira_erro_geracao():
    cliente = ClienteOllama(
        "http://127.0.0.1:1", "modelo-x", timeout=2, max_tokens=16, num_ctx=2048
    )
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


def test_criar_cliente_llm_repassa_num_ctx_ao_ollama():
    enviados = []
    config = settings.model_copy(update={"llm_provedor": "ollama", "llm_num_ctx": 12345})
    cliente = criar_cliente_llm(config)
    cliente._cliente = httpx.Client(
        base_url="http://ollama.falso",
        transport=httpx.MockTransport(
            lambda request: enviados.append(json.loads(request.content))
            or httpx.Response(200, json={"message": {"content": "ok"}, "done_reason": "stop"})
        ),
    )

    cliente.gerar("s", "u")

    assert enviados[0]["options"]["num_ctx"] == 12345


@pytest.mark.parametrize("chave", [None, SecretStr(""), SecretStr("   ")])
def test_criar_cliente_llm_anthropic_sem_chave_falha_cedo(chave):
    config = settings.model_copy(
        update={
            "llm_provedor": "anthropic",
            "llm_modelo": MODELO_ANTHROPIC_TESTE,
            "anthropic_api_key": chave,
        }
    )
    with pytest.raises(ErroGeracao, match="ANTHROPIC_API_KEY"):
        criar_cliente_llm(config)


def test_criar_cliente_llm_rejeita_provedor_desconhecido():
    with pytest.raises(ErroGeracao, match="LLM_PROVEDOR='antrophic'.*'ollama' ou 'anthropic'"):
        criar_cliente_llm(settings.model_copy(update={"llm_provedor": "antrophic"}))


def test_criar_cliente_llm_ignora_maiusculas_e_espacos_no_provedor():
    config = settings.model_copy(update={"llm_provedor": " Ollama "})
    assert isinstance(criar_cliente_llm(config), ClienteOllama)


def test_criar_cliente_llm_anthropic_com_modelo_de_outro_provedor_falha_cedo():
    config = settings.model_copy(
        update={
            "llm_provedor": "anthropic",
            "llm_modelo": "qwen2.5:7b",
            "anthropic_api_key": SecretStr("chave-de-teste"),
        }
    )
    with pytest.raises(ErroGeracao, match="LLM_MODELO='qwen2.5:7b'"):
        criar_cliente_llm(config)


def test_criar_cliente_llm_remove_espacos_do_modelo():
    config = settings.model_copy(update={"llm_provedor": "ollama", "llm_modelo": " qwen2.5:7b \n"})
    assert criar_cliente_llm(config)._modelo == "qwen2.5:7b"


@pytest.mark.parametrize("provedor", ["ollama", "anthropic"])
@pytest.mark.parametrize("modelo", ["", "   "])
def test_criar_cliente_llm_modelo_vazio_falha_cedo(provedor, modelo):
    config = settings.model_copy(
        update={
            "llm_provedor": provedor,
            "llm_modelo": modelo,
            "anthropic_api_key": SecretStr("chave-de-teste"),
        }
    )
    with pytest.raises(ErroGeracao, match="LLM_MODELO vazio"):
        criar_cliente_llm(config)


def test_criar_cliente_llm_anthropic_aceita_modelo_com_espacos():
    config = settings.model_copy(
        update={
            "llm_provedor": "anthropic",
            "llm_modelo": f"  {MODELO_ANTHROPIC_TESTE} ",
            "anthropic_api_key": SecretStr("chave-de-teste"),
        }
    )
    assert criar_cliente_llm(config)._modelo == MODELO_ANTHROPIC_TESTE


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
        settings.ollama_base_url, settings.llm_modelo, timeout=settings.llm_timeout, max_tokens=32,
        num_ctx=settings.llm_num_ctx,
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


class _MensagensFalsas:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok [1]")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=120, output_tokens=30),
        )


def _cliente_anthropic_falso(esforco=None):
    cliente = ClienteAnthropic(
        "claude-sonnet-5-5", timeout=5, max_tokens=100, api_key="x", esforco=esforco
    )
    mensagens = _MensagensFalsas()
    cliente._cliente = SimpleNamespace(messages=mensagens)
    return cliente, mensagens


def test_anthropic_registra_tokens_de_entrada_e_saida():
    cliente, _ = _cliente_anthropic_falso()

    saida = cliente.gerar("sistema", "usuario")

    assert (saida.tokens_entrada, saida.tokens_saida) == (120, 30)


def test_anthropic_envia_esforco_quando_configurado():
    cliente, mensagens = _cliente_anthropic_falso(esforco="low")

    cliente.gerar("sistema", "usuario")

    assert mensagens.kwargs["output_config"] == {"effort": "low"}
    assert "temperature" not in mensagens.kwargs


def test_anthropic_sem_esforco_nao_envia_output_config():
    cliente, mensagens = _cliente_anthropic_falso()

    cliente.gerar("sistema", "usuario")

    assert "output_config" not in mensagens.kwargs


def test_criar_cliente_llm_repassa_esforco_ao_anthropic():
    config = settings.model_copy(
        update={
            "llm_provedor": "anthropic",
            "llm_modelo": "claude-sonnet-5-5",
            "anthropic_api_key": SecretStr("chave-de-teste"),
            "llm_esforco": "medium",
        }
    )

    cliente = criar_cliente_llm(config)

    assert cliente._esforco == "medium"


def test_modelos_permitidos_comeca_pelo_padrao_sem_repetir():
    config = settings.model_copy(
        update={"llm_provedor": "ollama", "llm_modelo": "qwen2.5:7b", "llm_modelos": ["qwen2.5:14b", "qwen2.5:7b"]}
    )
    assert modelos_permitidos(config) == ["qwen2.5:7b", "qwen2.5:14b"]


def test_modelos_permitidos_fora_do_ollama_e_so_o_padrao():
    config = settings.model_copy(update={"llm_provedor": "anthropic", "llm_modelo": MODELO_ANTHROPIC_TESTE})
    assert modelos_permitidos(config) == [MODELO_ANTHROPIC_TESTE]


def test_modelos_instalados_le_as_tags_do_ollama():
    transporte = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "qwen2.5:14b"}]})
    )
    assert modelos_instalados(settings, transport=transporte) == {"qwen2.5:7b", "qwen2.5:14b"}


def test_modelos_instalados_sem_ollama_devolve_none():
    transporte = httpx.MockTransport(lambda request: httpx.Response(503))
    assert modelos_instalados(settings, transport=transporte) is None


def test_criar_cliente_llm_usa_o_modelo_pedido():
    config = settings.model_copy(update={"llm_provedor": "ollama", "llm_modelo": "qwen2.5:7b"})
    assert criar_cliente_llm(config, modelo="qwen2.5:14b")._modelo == "qwen2.5:14b"


def test_parametros_geracao_do_ollama():
    config = settings.model_copy(update={"llm_provedor": "ollama", "llm_max_tokens": 4096, "llm_num_ctx": 16384})
    assert parametros_geracao("qwen2.5:7b", config) == {
        "provedor": "ollama", "modelo": "qwen2.5:7b", "max_tokens": 4096, "temperatura": 0, "num_ctx": 16384,
    }
