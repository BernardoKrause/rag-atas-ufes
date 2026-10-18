from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean

from app.avaliacao.etapas import CONFIGS_GERACAO, CONFIGURACOES
from app.avaliacao.ground_truth import CATEGORIAS, PerguntaReferencia
from app.avaliacao.metricas import (
    cobertura_sequencia,
    ndcg_em_k,
    precisao_em_k,
    rank_reciproco,
    revocacao_em_k,
)

METRICAS_RAGAS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
PRECOS_POR_MTOK = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}
CATEGORIAS_COM_EVIDENCIA = tuple(c for c in CATEGORIAS if c != "sem_evidencia")


def _num(valor: float, casas: int = 3) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def _taxa(valor: float | None) -> str:
    return "n/d" if valor is None else _num(valor, 2)


def _grupos(perguntas: list[PerguntaReferencia]) -> list[tuple[str, set[str]]]:
    com_evidencia = [p for p in perguntas if p.categoria != "sem_evidencia"]
    grupos = [
        (categoria, {p.id for p in com_evidencia if p.categoria == categoria})
        for categoria in CATEGORIAS_COM_EVIDENCIA
    ]
    return [*grupos, ("todas", {p.id for p in com_evidencia})]


def tabela_recuperacao(perguntas: list[PerguntaReferencia], registros: list[dict]) -> str:
    relevantes = {p.id: set(p.itens_relevantes) for p in perguntas}
    linhas = [
        "| Config | Categoria | n | P@5 | R@5 | MRR | nDCG@5 |",
        "|---|---|---|---|---|---|---|",
    ]
    for config in CONFIGURACOES:
        por_id = {r["pergunta_id"]: r["ranking_logico"] for r in registros if r["config"] == config}
        for categoria, ids in _grupos(perguntas):
            ids = [i for i in ids if i in por_id]
            if not ids:
                continue
            valores = [
                (
                    precisao_em_k(por_id[i], relevantes[i]),
                    revocacao_em_k(por_id[i], relevantes[i]),
                    rank_reciproco(por_id[i], relevantes[i]),
                    ndcg_em_k(por_id[i], relevantes[i]),
                )
                for i in ids
            ]
            medias = [_num(mean(coluna)) for coluna in zip(*valores)]
            linhas.append(f"| {config} | {categoria} | {len(ids)} | " + " | ".join(medias) + " |")
    return "\n".join(linhas)


def tabela_ragas(perguntas: list[PerguntaReferencia], registros: list[dict]) -> str:
    linhas = [
        "| Config | Categoria | " + " | ".join(METRICAS_RAGAS) + " |",
        "|---|---|" + "---|" * len(METRICAS_RAGAS),
    ]
    for config in CONFIGS_GERACAO:
        do_config = [r for r in registros if r["config"] == config]
        for categoria, ids in _grupos(perguntas):
            selecionados = [r for r in do_config if r["pergunta_id"] in ids]
            if not selecionados:
                continue
            celulas = []
            for metrica in METRICAS_RAGAS:
                valores = [r[metrica] for r in selecionados if r[metrica] is not None]
                celulas.append(f"{_num(mean(valores))} ({len(valores)})" if valores else "– (0)")
            linhas.append(f"| {config} | {categoria} | " + " | ".join(celulas) + " |")
    return "\n".join(linhas)


def taxas_abstencao(
    perguntas: list[PerguntaReferencia], registros: list[dict]
) -> dict[str, dict[str, float | None]]:
    sem_evidencia = {p.id for p in perguntas if p.categoria == "sem_evidencia"}
    taxas = {}
    for config in CONFIGS_GERACAO:
        validos = [r for r in registros if r["config"] == config and not r["erro"]]
        sem = [r for r in validos if r["pergunta_id"] in sem_evidencia]
        com = [r for r in validos if r["pergunta_id"] not in sem_evidencia]
        taxas[config] = {
            "correta": sum(r["abstencao"] for r in sem) / len(sem) if sem else None,
            "indevida": sum(r["abstencao"] for r in com) / len(com) if com else None,
        }
    return taxas


def _usd(modelo: str, entrada: int, saida: int) -> float:
    preco_entrada, preco_saida = PRECOS_POR_MTOK[modelo]
    return (entrada * preco_entrada + saida * preco_saida) / 1_000_000


def custo(
    registros_geracao: list[dict],
    registros_ragas: list[dict],
    modelo_gerador: str,
    modelo_juiz: str,
) -> dict[str, float]:
    gerador = _usd(
        modelo_gerador,
        sum(r["tokens_entrada"] or 0 for r in registros_geracao),
        sum(r["tokens_saida"] or 0 for r in registros_geracao),
    )
    juiz = _usd(
        modelo_juiz,
        sum(r.get("tokens_juiz_entrada") or 0 for r in registros_ragas),
        sum(r.get("tokens_juiz_saida") or 0 for r in registros_ragas),
    )
    return {"gerador_usd": gerador, "juiz_usd": juiz, "total_usd": gerador + juiz}


def linhas_revisao(perguntas: list[PerguntaReferencia], descricoes: dict[str, dict]) -> list[dict]:
    linhas = []
    for p in perguntas:
        base = {
            "pergunta_id": p.id,
            "categoria": p.categoria,
            "origem": p.origem,
            "pergunta": p.pergunta,
            "resposta_referencia": p.resposta_referencia,
        }
        if not p.itens_relevantes:
            linhas.append(
                {
                    **base,
                    "item_id": "",
                    "orgao": "",
                    "data_reuniao": "",
                    "assunto": "",
                    "trecho_evidencia": "",
                    "texto_item": "",
                    "ordem_cronologica": "",
                    "correto": "",
                    "observacao": "",
                }
            )
            continue
        for item_id, trecho in zip(p.itens_relevantes, p.trechos_evidencia):
            descricao = descricoes.get(item_id, {})
            if item_id in p.sequencia_cronologica:
                ordem = p.sequencia_cronologica.index(item_id) + 1
            else:
                ordem = ""
            linhas.append(
                {
                    **base,
                    "item_id": item_id,
                    "orgao": descricao.get("orgao", ""),
                    "data_reuniao": descricao.get("data_reuniao", ""),
                    "assunto": descricao.get("assunto") or "",
                    "trecho_evidencia": trecho,
                    "texto_item": descricao.get("texto", ""),
                    "ordem_cronologica": ordem,
                    "correto": "",
                    "observacao": "",
                }
            )
    return linhas


def _ata(descricoes: dict[str, dict], item_id: str) -> str:
    descricao = descricoes.get(item_id)
    return f"{descricao['orgao']} {descricao['data_reuniao']}" if descricao else item_id


def linhas_diagnostico(
    perguntas: list[PerguntaReferencia],
    registros_geracao: list[dict],
    registros_recuperacao: list[dict],
    descricoes: dict[str, dict],
) -> list[dict]:
    geracao = {r["pergunta_id"]: r for r in registros_geracao if r["config"] == "A"}
    recuperacao = {r["pergunta_id"]: r for r in registros_recuperacao if r["config"] == "A"}
    linhas = []
    for p in perguntas:
        registro = geracao.get(p.id, {})
        relevantes = set(p.itens_relevantes)
        citadas = registro.get("fontes_logicas") or []
        atas_esperadas = {i.split("_")[0] for i in relevantes}
        cobertura = ""
        if p.sequencia_cronologica:
            encontrados = set(citadas) | set(recuperacao.get(p.id, {}).get("ranking_logico", []))
            cobertura = _num(cobertura_sequencia(encontrados, p.sequencia_cronologica), 2)
        linhas.append(
            {
                "pergunta_id": p.id,
                "categoria": p.categoria,
                "pergunta": p.pergunta,
                "resposta_referencia": p.resposta_referencia,
                "resposta_gerada": registro.get("texto") or "",
                "erro": registro.get("erro") or "",
                "abstencao": "sim" if registro.get("abstencao") else "não",
                "fontes_citadas": ";".join(citadas),
                "citou_relevante": "sim" if relevantes & set(citadas) else "não",
                "citou_ata_esperada": (
                    "sim" if any(c.split("_")[0] in atas_esperadas for c in citadas) else "não"
                ),
                "fontes_fora_do_gabarito": ";".join(c for c in citadas if c not in relevantes),
                "atas_citadas": "; ".join(_ata(descricoes, c) for c in citadas),
                "atas_esperadas": "; ".join(_ata(descricoes, i) for i in p.itens_relevantes),
                "cobertura_sequencia": cobertura,
                "ordem_cronologica_correta": "",
                "diagnostico": "",
                "observacao": "",
            }
        )
    return linhas


def escrever_csv(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)


def montar_relatorio(
    perguntas: list[PerguntaReferencia],
    rec: list[dict],
    ger: list[dict],
    rag: list[dict],
    modelo_gerador: str,
    modelo_juiz: str,
) -> str:
    taxas = taxas_abstencao(perguntas, ger)
    valores_custo = custo(ger, rag, modelo_gerador, modelo_juiz)
    erros_geracao = sum(1 for r in ger if r["erro"] and r["erro"] != "truncada")
    truncadas = sum(1 for r in ger if r["truncada"])
    erros_ragas = sum(len(r["erros"]) for r in rag)
    linhas_abstencao = [
        f"| {c} | {_taxa(t['correta'])} | {_taxa(t['indevida'])} |" for c, t in taxas.items()
    ]
    return "\n".join(
        [
            "## Recuperação",
            "",
            tabela_recuperacao(perguntas, rec),
            "",
            "## Geração (RAGAS)",
            "",
            "Média por métrica, com o número de respostas avaliadas entre parênteses.",
            "",
            tabela_ragas(perguntas, rag),
            "",
            "## Abstenção",
            "",
            "| Config | Correta | Indevida |",
            "|---|---|---|",
            *linhas_abstencao,
            "",
            f"Erros de geração: {erros_geracao}. Respostas truncadas: {truncadas}. "
            f"Métricas RAGAS sem valor: {erros_ragas}.",
            "",
            "## Custo",
            "",
            f"Gerador ({modelo_gerador}): US$ {_num(valores_custo['gerador_usd'], 2)}. "
            f"Juiz ({modelo_juiz}): US$ {_num(valores_custo['juiz_usd'], 2)}. "
            f"Total: US$ {_num(valores_custo['total_usd'], 2)}.",
        ]
    )
