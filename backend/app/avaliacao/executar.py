from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import anthropic
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.avaliacao.etapas import etapa_geracao, etapa_recuperacao, montar_pool
from app.avaliacao.ground_truth import carregar_ground_truth, validar_ground_truth
from app.avaliacao.itens import descrever_itens, mapa_item_logico
from app.avaliacao.jsonl import ler_jsonl
from app.avaliacao.relatorio import (
    escrever_csv,
    linhas_diagnostico,
    linhas_revisao,
    montar_relatorio,
)
from app.core.config import REPO_ROOT, settings
from app.geracao.tipos import ErroGeracao

MODELO_GERADOR = "claude-sonnet-5-5"
DIR_AVALIACAO = REPO_ROOT / "docs" / "avaliacao"
ETAPAS = (
    "validar",
    "pool",
    "revisao",
    "recuperacao",
    "geracao",
    "ragas",
    "relatorio",
    "diagnostico",
)
ETAPAS_COM_RODADA = ("recuperacao", "geracao", "ragas", "relatorio", "diagnostico")
COLUNAS_DESCRICAO = ("orgao", "data_reuniao", "assunto")


def carregar_perguntas(caminho: Path, filtro: str | None):
    perguntas = carregar_ground_truth(caminho)
    if filtro:
        ids = set(filtro.split(","))
        perguntas = [p for p in perguntas if p.id in ids]
    return perguntas


def _clientes():
    from app.grafo.cliente import obter_driver
    from app.ingestion.indexador import _obter_cliente_qdrant

    sessao = sessionmaker(bind=create_engine(settings.database_url))
    return sessao, _obter_cliente_qdrant(), obter_driver()


def _recuperar_ids(sessao, cliente_qdrant, driver):
    from app.recuperacao.orquestrador import recuperar

    def recuperar_ids(pergunta, camadas, k):
        evidencias = recuperar(pergunta, sessao, cliente_qdrant, driver, k=k, camadas=camadas)
        return [e.item_id_canonico for e in evidencias]

    return recuperar_ids


def _linhas_pool(linhas, descricoes):
    saida = []
    for linha in linhas:
        descricao = descricoes.get(linha["item_id"], {})
        extras = {coluna: descricao.get(coluna) or "" for coluna in COLUNAS_DESCRICAO}
        saida.append(
            {**linha, **extras, "texto_item": descricao.get("texto", ""), "relevante": ""}
        )
    return saida


def _rodar(args, perguntas) -> int:
    pasta = DIR_AVALIACAO / "resultados" / (args.rodada or "")
    Sessao, cliente_qdrant, driver = _clientes()
    try:
        with Sessao() as sessao:
            if args.etapa == "validar":
                erros = validar_ground_truth(perguntas, set(mapa_item_logico(sessao).values()))
                print("\n".join(erros) or f"{len(perguntas)} perguntas válidas")
                return 1 if erros else 0
            if args.etapa == "pool":
                linhas = montar_pool(
                    perguntas,
                    _recuperar_ids(sessao, cliente_qdrant, driver),
                    mapa_item_logico(sessao),
                )
                descricoes = descrever_itens(sessao, {linha["item_id"] for linha in linhas})
                escrever_csv(DIR_AVALIACAO / "pool.csv", _linhas_pool(linhas, descricoes))
            elif args.etapa == "revisao":
                ids = {i for p in perguntas for i in p.itens_relevantes}
                escrever_csv(
                    DIR_AVALIACAO / "ground_truth_revisao.csv",
                    linhas_revisao(perguntas, descrever_itens(sessao, ids)),
                )
            elif args.etapa == "recuperacao":
                total = etapa_recuperacao(
                    perguntas,
                    _recuperar_ids(sessao, cliente_qdrant, driver),
                    mapa_item_logico(sessao),
                    pasta / "recuperacao.jsonl",
                )
                print(f"{total} registros de recuperação")
            elif args.etapa == "geracao":
                from app.geracao.llm import criar_cliente_llm
                from app.geracao.respondedor import responder_detalhado

                cliente_llm = criar_cliente_llm()

                def responder_fn(pergunta, camadas):
                    return responder_detalhado(
                        pergunta, sessao, cliente_qdrant, driver, cliente_llm, camadas=camadas
                    )

                total = etapa_geracao(
                    perguntas,
                    responder_fn,
                    mapa_item_logico(sessao),
                    pasta / "geracao.jsonl",
                    MODELO_GERADOR,
                )
                print(f"{total} respostas geradas")
            elif args.etapa == "ragas":
                from anthropic import AsyncAnthropic

                from app.avaliacao.ragas_avaliacao import (
                    EmbeddingsSerafim,
                    JuizAnthropic,
                    criar_metricas,
                    etapa_ragas,
                )

                chave = settings.anthropic_api_key.get_secret_value()
                juiz = JuizAnthropic(AsyncAnthropic(api_key=chave))
                total = etapa_ragas(
                    perguntas,
                    pasta / "geracao.jsonl",
                    pasta / "ragas.jsonl",
                    criar_metricas(juiz, EmbeddingsSerafim()),
                    juiz,
                )
                print(f"{total} respostas avaliadas pelo RAGAS")
            elif args.etapa == "relatorio":
                from app.avaliacao.ragas_avaliacao import MODELO_JUIZ

                texto = montar_relatorio(
                    perguntas,
                    ler_jsonl(pasta / "recuperacao.jsonl"),
                    ler_jsonl(pasta / "geracao.jsonl"),
                    ler_jsonl(pasta / "ragas.jsonl"),
                    MODELO_GERADOR,
                    MODELO_JUIZ,
                )
                (pasta / "relatorio.md").write_text(texto + "\n", encoding="utf-8")
                print(texto)
            elif args.etapa == "diagnostico":
                geracao = ler_jsonl(pasta / "geracao.jsonl")
                ids = {i for p in perguntas for i in p.itens_relevantes}
                ids |= {f for r in geracao for f in r["fontes_logicas"]}
                escrever_csv(
                    pasta / "diagnostico.csv",
                    linhas_diagnostico(
                        perguntas,
                        geracao,
                        ler_jsonl(pasta / "recuperacao.jsonl"),
                        descrever_itens(sessao, ids),
                    ),
                )
    finally:
        driver.close()
        cliente_qdrant.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avaliação final do sistema (Parte 11).")
    parser.add_argument("etapa", choices=ETAPAS)
    parser.add_argument("--rodada")
    parser.add_argument("--ground-truth", type=Path, default=DIR_AVALIACAO / "ground_truth.yaml")
    parser.add_argument("--perguntas")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    if args.etapa in ETAPAS_COM_RODADA and not args.rodada:
        print(f"a etapa {args.etapa} exige --rodada", file=sys.stderr)
        return 1
    if args.etapa == "geracao" and (
        settings.llm_provedor.strip().lower() != "anthropic"
        or settings.llm_modelo.strip() != MODELO_GERADOR
    ):
        print(
            f"a geração da avaliação exige LLM_PROVEDOR=anthropic e LLM_MODELO={MODELO_GERADOR}",
            file=sys.stderr,
        )
        return 1
    try:
        return _rodar(args, carregar_perguntas(args.ground_truth, args.perguntas))
    except (anthropic.APIError, ErroGeracao) as erro:
        print(
            f"falha na API da Anthropic: {erro}. Rode o mesmo comando de novo para retomar.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
