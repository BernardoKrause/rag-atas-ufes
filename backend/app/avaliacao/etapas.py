from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx

from app.avaliacao.ground_truth import PerguntaReferencia
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.avaliacao.metricas import agrupar_fragmentos
from app.geracao.tipos import ErroGeracao, RespostaDetalhada

logger = logging.getLogger(__name__)

CONFIGURACOES = {
    "A": frozenset({"lexico", "vetorial", "grafo"}),
    "B": frozenset({"lexico", "vetorial"}),
    "C": frozenset({"lexico"}),
    "D": frozenset({"vetorial"}),
}
CONFIGS_GERACAO = ("A", "B")

RecuperarIds = Callable[[str, frozenset[str], int], list[str]]
ResponderFn = Callable[[str, frozenset[str]], RespostaDetalhada]


def etapa_recuperacao(
    perguntas: list[PerguntaReferencia],
    recuperar_ids: RecuperarIds,
    mapa_logico: dict[str, str],
    saida: Path,
    k: int = 5,
) -> int:
    saida.unlink(missing_ok=True)
    total = 0
    for pergunta in perguntas:
        for config, camadas in CONFIGURACOES.items():
            ranking = recuperar_ids(pergunta.pergunta, camadas, k)
            anexar_jsonl(saida, {
                "pergunta_id": pergunta.id,
                "config": config,
                "ranking": ranking,
                "ranking_logico": agrupar_fragmentos(ranking, mapa_logico),
            })
            total += 1
    return total


def _registro_geracao(
    pergunta_id: str, config: str, modelo: str, detalhada: RespostaDetalhada,
    mapa_logico: dict[str, str],
) -> dict:
    fontes = [fonte.item_id_canonico for fonte in detalhada.resposta.fontes]
    saida_llm = detalhada.saida_llm
    return {
        "pergunta_id": pergunta_id,
        "config": config,
        "modelo": modelo,
        "texto": detalhada.resposta.texto,
        "abstencao": detalhada.resposta.abstencao,
        "fontes": fontes,
        "fontes_logicas": agrupar_fragmentos(fontes, mapa_logico),
        "contextos": [
            "\n".join([evidencia.fonte.rotulo, evidencia.texto, *evidencia.frases_grafo])
            for evidencia in detalhada.evidencias
        ],
        "tokens_entrada": saida_llm.tokens_entrada if saida_llm else None,
        "tokens_saida": saida_llm.tokens_saida if saida_llm else None,
        "truncada": saida_llm.truncada if saida_llm else False,
        "erro": None,
    }


def _registro_erro(pergunta_id: str, config: str, modelo: str, erro: Exception) -> dict:
    return {
        "pergunta_id": pergunta_id, "config": config, "modelo": modelo, "texto": None,
        "abstencao": None, "fontes": [], "fontes_logicas": [], "contextos": [],
        "tokens_entrada": None, "tokens_saida": None, "truncada": False, "erro": str(erro),
    }


def etapa_geracao(
    perguntas: list[PerguntaReferencia],
    responder_fn: ResponderFn,
    mapa_logico: dict[str, str],
    saida: Path,
    modelo: str,
) -> int:
    feitos = {(r["pergunta_id"], r["config"]) for r in ler_jsonl(saida)}
    total = 0
    for pergunta in perguntas:
        for config in CONFIGS_GERACAO:
            if (pergunta.id, config) in feitos:
                continue
            try:
                detalhada = responder_fn(pergunta.pergunta, CONFIGURACOES[config])
                registro = _registro_geracao(pergunta.id, config, modelo, detalhada, mapa_logico)
                if detalhada.saida_llm and detalhada.saida_llm.truncada:
                    registro["erro"] = "truncada"
            except ErroGeracao as erro:
                if isinstance(erro.__cause__, (anthropic.APIError, httpx.HTTPError)):
                    raise
                logger.warning("geração falhou em %s/%s: %s", pergunta.id, config, erro)
                registro = _registro_erro(pergunta.id, config, modelo, erro)
            anexar_jsonl(saida, registro)
            total += 1
    return total


def montar_pool(
    perguntas: list[PerguntaReferencia],
    recuperar_ids: RecuperarIds,
    mapa_logico: dict[str, str],
    k: int = 10,
) -> list[dict]:
    linhas = []
    for pergunta in perguntas:
        por_item: dict[str, dict] = {}
        for config, camadas in CONFIGURACOES.items():
            ranking = agrupar_fragmentos(recuperar_ids(pergunta.pergunta, camadas, k), mapa_logico)
            for posicao, item_id in enumerate(ranking, start=1):
                linha = por_item.setdefault(
                    item_id,
                    {
                        "pergunta_id": pergunta.id,
                        "item_id": item_id,
                        "configs": [],
                        "melhor_rank": posicao,
                    },
                )
                linha["configs"].append(config)
                linha["melhor_rank"] = min(linha["melhor_rank"], posicao)
        ordenadas = sorted(
            por_item.values(), key=lambda linha_pool: (linha_pool["melhor_rank"], linha_pool["item_id"])
        )
        for linha in ordenadas:
            linhas.append({**linha, "configs": ",".join(linha["configs"])})
    return linhas
