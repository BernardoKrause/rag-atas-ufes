from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonte:
    numero: int
    item_id_canonico: str
    documento_id: int
    rotulo: str
    trecho: str
    pagina: int | None


@dataclass(frozen=True)
class EvidenciaNumerada:
    numero: int
    fonte: Fonte
    texto: str
    frases_grafo: list[str]
    assunto_anterior: str | None
    assunto_posterior: str | None


@dataclass(frozen=True)
class Resposta:
    texto: str
    fontes: list[Fonte]
    abstencao: bool


@dataclass(frozen=True)
class SaidaLLM:
    texto: str
    truncada: bool
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


@dataclass(frozen=True)
class RespostaDetalhada:
    resposta: Resposta
    evidencias: list[EvidenciaNumerada]
    saida_llm: SaidaLLM | None


class ErroGeracao(Exception):
    pass
