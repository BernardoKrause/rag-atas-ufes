from __future__ import annotations

import json
from typing import Protocol

import anthropic
import httpx

from app.core.config import Settings, settings
from app.geracao.tipos import ErroGeracao, SaidaLLM


class ClienteLLM(Protocol):
    def gerar(self, sistema: str, usuario: str, esquema: dict | None = None) -> SaidaLLM: ...


class ClienteOllama:
    def __init__(
        self,
        base_url: str,
        modelo: str,
        timeout: float,
        max_tokens: int,
        num_ctx: int,
        transport: httpx.BaseTransport | None = None,
    ):
        self._cliente = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._modelo = modelo
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx

    def gerar(self, sistema: str, usuario: str, esquema: dict | None = None) -> SaidaLLM:
        corpo_pedido = {
            "model": self._modelo,
            "stream": False,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "options": {
                "temperature": 0,
                "num_predict": self._max_tokens,
                "num_ctx": self._num_ctx,
            },
        }
        if esquema is not None:
            corpo_pedido["format"] = esquema
        try:
            resposta = self._cliente.post("/api/chat", json=corpo_pedido)
            resposta.raise_for_status()
        except httpx.HTTPError as erro:
            raise ErroGeracao(f"falha ao chamar o Ollama: {erro}") from erro
        try:
            corpo = resposta.json()
            texto = corpo["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as erro:
            raise ErroGeracao(f"resposta inesperada do Ollama: {erro}") from erro
        return SaidaLLM(
            texto=texto,
            truncada=corpo.get("done_reason") == "length",
            tokens_entrada=corpo.get("prompt_eval_count"),
            tokens_saida=corpo.get("eval_count"),
        )


class ClienteAnthropic:
    def __init__(
        self,
        modelo: str,
        timeout: float,
        max_tokens: int,
        api_key: str | None = None,
        esforco: str | None = None,
    ):
        self._cliente = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._modelo = modelo
        self._max_tokens = max_tokens
        self._esforco = esforco

    def gerar(self, sistema: str, usuario: str, esquema: dict | None = None) -> SaidaLLM:
        extras = {"output_config": {"effort": self._esforco}} if self._esforco else {}
        try:
            mensagem = self._cliente.messages.create(
                model=self._modelo,
                max_tokens=self._max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": usuario}],
                **extras,
            )
        except anthropic.APIError as erro:
            raise ErroGeracao(f"falha ao chamar a API da Anthropic: {erro}") from erro
        if mensagem.stop_reason == "refusal":
            raise ErroGeracao("a API da Anthropic recusou a requisição")
        texto = "".join(bloco.text for bloco in mensagem.content if bloco.type == "text")
        return SaidaLLM(
            texto=texto,
            truncada=mensagem.stop_reason == "max_tokens",
            tokens_entrada=mensagem.usage.input_tokens,
            tokens_saida=mensagem.usage.output_tokens,
        )


def modelos_permitidos(config: Settings = settings) -> list[str]:
    padrao = config.llm_modelo.strip()
    if config.llm_provedor.strip().lower() != "ollama":
        return [padrao]
    nomes = [padrao] + [nome.strip() for nome in config.llm_modelos if nome.strip()]
    return list(dict.fromkeys(nomes))


def modelos_instalados(config: Settings = settings, transport: httpx.BaseTransport | None = None) -> set[str] | None:
    try:
        with httpx.Client(base_url=config.ollama_base_url, timeout=5.0, transport=transport) as cliente:
            resposta = cliente.get("/api/tags")
            resposta.raise_for_status()
            return {modelo["name"] for modelo in resposta.json().get("models", [])}
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return None


def parametros_geracao(modelo: str, config: Settings = settings) -> dict:
    parametros = {"provedor": config.llm_provedor.strip().lower(), "modelo": modelo, "max_tokens": config.llm_max_tokens}
    if parametros["provedor"] == "ollama":
        parametros |= {"temperatura": 0, "num_ctx": config.llm_num_ctx}
    return parametros


def criar_cliente_llm(config: Settings = settings, modelo: str | None = None) -> ClienteLLM:
    provedor = config.llm_provedor.strip().lower()
    modelo = (modelo or config.llm_modelo).strip()
    if not modelo:
        raise ErroGeracao("LLM_MODELO vazio no .env")
    if provedor == "ollama":
        return ClienteOllama(
            config.ollama_base_url, modelo, config.llm_timeout, config.llm_max_tokens,
            config.llm_num_ctx,
        )
    if provedor == "anthropic":
        segredo = config.anthropic_api_key
        chave = segredo.get_secret_value().strip() if segredo else ""
        if not chave:
            raise ErroGeracao("LLM_PROVEDOR=anthropic exige ANTHROPIC_API_KEY no .env")
        if not modelo.startswith("claude-"):
            raise ErroGeracao(
                f"LLM_MODELO={config.llm_modelo!r} não é um modelo da Anthropic "
                "(esperado 'claude-...')"
            )
        esforco = (config.llm_esforco or "").strip().lower() or None
        return ClienteAnthropic(
            modelo, config.llm_timeout, config.llm_max_tokens, chave, esforco=esforco
        )
    raise ErroGeracao(
        f"LLM_PROVEDOR={config.llm_provedor!r} inválido; use 'ollama' ou 'anthropic'"
    )
