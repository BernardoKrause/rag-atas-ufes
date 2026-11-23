from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.avaliacao import manifesto
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.avaliacao.metricas_rodada import agregar, avaliar_ranking, ranking_logico, relevantes_da_referencia
from app.avaliacao.rodada import CONDICOES, K, carregar_referencia, contexto_da_execucao, registrar_etapa
from app.recuperacao.setor import NOMES_POR_EXTENSO, RE_SETOR

logger = logging.getLogger(__name__)

MODOS_SETOR = ("hibrida", "expandida")


def variantes_setor(enunciado: str, orgao: str | None) -> dict[str, str]:
    match = RE_SETOR.search(enunciado)
    if not match:
        return {"original": enunciado}
    antes, depois = enunciado[:match.start()], enunciado[match.end():]
    variantes = {
        "original": enunciado,
        "sem_setor": (antes.rstrip() + depois).strip(),
        "sigla_solta": f"{antes}no {match.group(1)}{depois}",
    }
    if orgao in NOMES_POR_EXTENSO:
        variantes["nome_por_extenso"] = f"{antes}no {NOMES_POR_EXTENSO[orgao]}{depois}"
    return variantes


VARIANTES_SELETOR = ("original", "sem_setor")


def etapa_setor(referencias: list[dict], saida: Path, sessao, qdrant, driver, seletor: bool = False) -> int:
    from app.recuperacao.orquestrador import recuperar

    arquivo = saida / ("seletor.jsonl" if seletor else "setor.jsonl")
    feitos = {(r["pergunta_id"], r["variante"], r["modo"]) for r in ler_jsonl(arquivo)}
    total = 0
    for referencia in referencias:
        for variante, enunciado in variantes_setor(referencia["enunciado"], referencia["orgao"]).items():
            if seletor and variante not in VARIANTES_SELETOR:
                continue
            for modo in MODOS_SETOR:
                if (referencia["identificador"], variante, modo) in feitos:
                    continue
                rastreio = {}
                recuperar(
                    enunciado, sessao, qdrant, driver, k=K, camadas=CONDICOES[modo], registro=rastreio,
                    orgao=referencia["orgao"] if seletor else None,
                )
                anexar_jsonl(arquivo, {
                    "pergunta_id": referencia["identificador"], "variante": variante, "modo": modo,
                    "enunciado": enunciado, "orgao_esperado": referencia["orgao"],
                    "orgao_identificado": rastreio["orgao"], "ids_finais": rastreio["ids_finais"],
                })
                total += 1
    return total


def resumir_setor(referencias: list[dict], saida: Path, mapa: dict[str, str], nome: str = "setor") -> dict:
    relevantes = {r["identificador"]: relevantes_da_referencia(r, mapa)[0] for r in referencias}
    grupos, linhas = defaultdict(list), []
    for registro in ler_jsonl(saida / f"{nome}.jsonl"):
        g = relevantes.get(registro["pergunta_id"])
        if g is None:
            continue
        avaliacao = avaliar_ranking(ranking_logico(registro["ids_finais"], mapa), g, K)
        linha = {
            "pergunta_id": registro["pergunta_id"], "variante": registro["variante"], "modo": registro["modo"],
            "orgao_esperado": registro["orgao_esperado"], "orgao_identificado": registro["orgao_identificado"],
            **{c: avaliacao[c] for c in ("tp", "relevantes", "precisao", "revocacao", "rr", "ndcg")},
        }
        linhas.append(linha)
        grupos[(registro["variante"], registro["modo"])].append((linha, avaliacao))
    resumo = {}
    for (variante, modo), itens in sorted(grupos.items()):
        resumo[f"{variante}/{modo}"] = {
            "consultas": len(itens),
            "orgao_correto": sum(1 for linha, _ in itens if linha["orgao_identificado"] == linha["orgao_esperado"]),
            "sem_orgao": sum(1 for linha, _ in itens if linha["orgao_identificado"] is None),
            **agregar([a for _, a in itens]),
        }
    (saida / f"{nome}_por_pergunta.jsonl").write_text(
        "".join(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas), encoding="utf-8"
    )
    (saida / f"{nome}_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumo


def etapa_abstencao(perguntas: list[dict], saida: Path, condicoes: list[str], sessao, qdrant, driver, cliente_llm) -> int:
    from app.geracao.respondedor import responder_detalhado

    arquivo = saida / "abstencao.jsonl"
    feitos = {(r["pergunta_id"], r["condicao"]) for r in ler_jsonl(arquivo)}
    total = 0
    for pergunta in perguntas:
        for condicao in condicoes:
            if (pergunta["identificador"], condicao) in feitos:
                continue
            rastreio = {}
            inicio = time.monotonic()
            detalhada = responder_detalhado(
                pergunta["enunciado"], sessao, qdrant, driver, cliente_llm,
                camadas=CONDICOES[condicao], k=K, registro=rastreio,
            )
            anexar_jsonl(arquivo, {
                "pergunta_id": pergunta["identificador"], "condicao": condicao, "enunciado": pergunta["enunciado"],
                "origem": pergunta.get("origem"), "variacao": pergunta.get("variacao"),
                "segundos": round(time.monotonic() - inicio, 2),
                "abstencao": detalhada.resposta.abstencao, "texto": detalhada.resposta.texto,
                "fontes": [f.item_id_canonico for f in detalhada.resposta.fontes], "rastreio": rastreio,
            })
            total += 1
            print(pergunta["identificador"], condicao, "abstenção" if detalhada.resposta.abstencao else "respondeu", flush=True)
    return total


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(description="Experimentos complementares: filtro por setor e abstenção.")
    parser.add_argument("etapa", choices=("setor", "seletor", "abstencao"))
    parser.add_argument("--referencia", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--perguntas", type=Path, help="JSONL com as perguntas sem resposta (etapa abstencao)")
    parser.add_argument("--condicoes", default="hibrida,expandida_campos")
    argumentos = parser.parse_args(argv)

    from app.avaliacao.executar import _clientes
    from app.avaliacao.itens import mapa_item_logico
    from app.avaliacao.ragas_avaliacao import MODELO_JUIZ

    saida = argumentos.saida
    saida.mkdir(parents=True, exist_ok=True)
    referencias = carregar_referencia(argumentos.referencia)
    inicio = manifesto.agora()
    Sessao, qdrant, driver = _clientes()
    extras: dict = {"situacao": "interrompida"}
    try:
        with Sessao() as sessao:
            extras["ambiente"] = contexto_da_execucao(argumentos.referencia, sessao, qdrant, driver, MODELO_JUIZ)
            sessao.rollback()
            if argumentos.etapa in ("setor", "seletor"):
                seletor = argumentos.etapa == "seletor"
                extras["registros_novos"] = etapa_setor(referencias, saida, sessao, qdrant, driver, seletor=seletor)
                extras["resumo"] = resumir_setor(referencias, saida, mapa_item_logico(sessao), nome=argumentos.etapa)
            else:
                from app.geracao.llm import criar_cliente_llm

                perguntas = ler_jsonl(argumentos.perguntas)
                extras["perguntas_arquivo"] = {
                    "nome": argumentos.perguntas.name, "sha256": manifesto.sha256_arquivo(argumentos.perguntas),
                }
                condicoes = [c for c in argumentos.condicoes.split(",") if c]
                extras["registros_novos"] = etapa_abstencao(
                    perguntas, saida, condicoes, sessao, qdrant, driver, criar_cliente_llm()
                )
            extras["situacao"] = "concluida"
    except BaseException as erro:
        extras["erro"] = f"{type(erro).__name__}: {erro}"
        raise
    finally:
        registrar_etapa(saida, f"experimento_{argumentos.etapa}", inicio, extras)
        driver.close()
        qdrant.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
