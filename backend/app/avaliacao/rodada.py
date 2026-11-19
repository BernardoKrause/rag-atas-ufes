from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

from app.avaliacao import manifesto
from app.avaliacao.jsonl import anexar_jsonl, ler_jsonl
from app.avaliacao.metricas_rodada import (
    agregar,
    avaliar_ranking,
    linhas_do_ranking,
    origem_por_item,
    ranking_logico,
    relevantes_da_referencia,
)
from app.core.config import settings
from app.geracao.tipos import ErroGeracao

logger = logging.getLogger(__name__)

CONDICOES = {
    "hibrida": frozenset({"lexico", "vetorial"}),
    "hibrida_campos": frozenset({"lexico", "vetorial", "campos_grafo"}),
    "expandida": frozenset({"lexico", "vetorial", "grafo"}),
    "expandida_campos": frozenset({"lexico", "vetorial", "grafo", "campos_grafo"}),
}
SO_RECUPERACAO = {
    "lexico": frozenset({"lexico"}),
    "vetorial": frozenset({"vetorial"}),
    "hibrida": CONDICOES["hibrida"],
    "expandida": CONDICOES["expandida"],
}
EQUIVALENTE_NA_RODADA_ANTERIOR = {"expandida_campos": "A", "hibrida": "B"}
MESMA_RECUPERACAO = {"hibrida_campos": "hibrida", "expandida_campos": "expandida"}
K_CURVA = 20
K = 5
CONDICOES_K_AMPLIADO = ("hibrida", "expandida_campos")
METRICAS_RAGAS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
TEMPO_LIMITE_JUIZ = 1800.0
MAXIMO_ERROS_SEGUIDOS = 5


def carregar_referencia(caminho: Path, filtro: set[str] | None = None) -> list[dict]:
    registros = [r for r in ler_jsonl(caminho) if r["entra_na_avaliacao"]]
    return [r for r in registros if not filtro or r["identificador"] in filtro]


def sem_evidencia(referencia: dict) -> bool:
    return not referencia["evidencias"]


def _clientes():
    from app.avaliacao.executar import _clientes as clientes

    return clientes()


def registrar_etapa(saida: Path, etapa: str, inicio: str, extras: dict) -> None:
    caminho = saida / "manifesto.json"
    atual = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {
        "rodada": saida.name,
        "criada_em": inicio,
        "condicoes": {nome: sorted(camadas) for nome, camadas in CONDICOES.items()},
        "equivalente_na_rodada_anterior": EQUIVALENTE_NA_RODADA_ANTERIOR,
        "etapas": [],
    }
    atual["etapas"].append({"etapa": etapa, "inicio": inicio, "fim": manifesto.agora(), **extras})
    caminho.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")


def contexto_da_execucao(referencia: Path, sessao, qdrant, driver, modelo_juiz: str) -> dict:
    registros = ler_jsonl(referencia)
    return {
        "codigo": manifesto.versao_do_codigo(),
        "referencia": {
            "arquivo": referencia.name,
            "sha256": manifesto.sha256_arquivo(referencia),
            "versoes": sorted({r["versao"] for r in registros}),
            "registros": len(registros),
            "na_avaliacao": sum(r["entra_na_avaliacao"] for r in registros),
        },
        "dados": manifesto.versao_dos_dados(sessao, qdrant, driver),
        "modelos": manifesto.versao_dos_modelos(modelo_juiz),
        "parametros": manifesto.parametros(),
        "ambiente": manifesto.ambiente(),
    }


def etapa_recuperacao(referencias: list[dict], saida: Path, sessao, qdrant, driver) -> int:
    from app.recuperacao.orquestrador import recuperar

    arquivo = saida / "recuperacao.jsonl"
    feitos = {(r["pergunta_id"], r["modo"]) for r in ler_jsonl(arquivo)}
    total = 0
    for referencia in referencias:
        for modo, camadas in SO_RECUPERACAO.items():
            if (referencia["identificador"], modo) in feitos:
                continue
            rastreio = {}
            inicio = time.monotonic()
            recuperar(referencia["enunciado"], sessao, qdrant, driver, k=K_CURVA, camadas=camadas, registro=rastreio)
            anexar_jsonl(arquivo, {
                "pergunta_id": referencia["identificador"], "modo": modo, "enunciado": referencia["enunciado"],
                "segundos": round(time.monotonic() - inicio, 2), "rastreio": rastreio,
            })
            total += 1
    return total


def contextos_ragas(rastreio: dict) -> list[str]:
    return ["\n".join([c["rotulo"], c["texto"], *c["frases_grafo"]]) for c in rastreio["contexto"]]


def etapa_geracao(
    referencias: list[dict], saida: Path, arquivo: Path, repeticao: int, condicoes: list[str],
    sessao, qdrant, driver, cliente_llm, k_por_pergunta: dict[str, int] | None = None,
) -> int:
    from app.geracao.respondedor import responder_detalhado

    feitos = {(r["pergunta_id"], r["condicao"]) for r in ler_jsonl(arquivo)}
    erros_seguidos, total = 0, 0
    for referencia in referencias:
        pergunta_id = referencia["identificador"]
        for condicao in condicoes:
            if (pergunta_id, condicao) in feitos:
                continue
            k = (k_por_pergunta or {}).get(pergunta_id, K)
            rastreio = {}
            inicio_relogio, inicio = manifesto.agora(), time.monotonic()
            try:
                detalhada = responder_detalhado(
                    referencia["enunciado"], sessao, qdrant, driver, cliente_llm,
                    camadas=CONDICOES[condicao], k=k, registro=rastreio,
                )
            except (ErroGeracao, httpx.HTTPError) as erro:
                sessao.rollback()
                anexar_jsonl(saida / "erros.jsonl", {
                    "arquivo": arquivo.name, "pergunta_id": pergunta_id, "condicao": condicao,
                    "repeticao": repeticao, "quando": inicio_relogio, "erro": f"{type(erro).__name__}: {erro}",
                })
                logger.warning("geração falhou em %s/%s: %s", pergunta_id, condicao, erro)
                erros_seguidos += 1
                if erros_seguidos >= MAXIMO_ERROS_SEGUIDOS:
                    raise RuntimeError(f"{MAXIMO_ERROS_SEGUIDOS} erros seguidos; rodada interrompida") from erro
                continue
            erros_seguidos = 0
            anexar_jsonl(arquivo, {
                "pergunta_id": pergunta_id, "condicao": condicao, "repeticao": repeticao, "k": k,
                "enunciado": referencia["enunciado"], "inicio": inicio_relogio,
                "segundos": round(time.monotonic() - inicio, 2),
                "texto": detalhada.resposta.texto, "abstencao": detalhada.resposta.abstencao,
                "fontes": [f.item_id_canonico for f in detalhada.resposta.fontes],
                "contextos": contextos_ragas(rastreio),
                "truncada": any(c["truncada"] for c in rastreio["chamadas_eventos"])
                or bool(rastreio["chamada_resposta"] and rastreio["chamada_resposta"]["truncada"]),
                "rastreio": rastreio,
            })
            total += 1
            print(f"{pergunta_id} {condicao} r{repeticao} k={k} {round(time.monotonic() - inicio)}s", flush=True)
    return total


def referencias_anonimizadas(referencias: list[dict], saida: Path, sessao) -> dict[str, str]:
    from app.ingestion.cleaner import anonimizar_texto

    arquivo = saida / "referencias_anonimizadas.jsonl"
    prontas = {r["pergunta_id"]: r["referencia"] for r in ler_jsonl(arquivo)}
    chave = settings.anonymization_secret_key.get_secret_value().encode()
    try:
        for referencia in referencias:
            if referencia["identificador"] in prontas or not referencia["resposta_esperada"]:
                continue
            texto, _ = anonimizar_texto(referencia["resposta_esperada"], chave, sessao)
            anexar_jsonl(arquivo, {"pergunta_id": referencia["identificador"], "referencia": texto})
            prontas[referencia["identificador"]] = texto
    finally:
        sessao.rollback()
    return prontas


def entrada_ragas(pergunta: str, registro: dict, referencia: str) -> str:
    return manifesto.sha256_texto(json.dumps(
        [pergunta, registro["texto"], registro["abstencao"], registro["contextos"], referencia], ensure_ascii=False
    ))


def reaproveitavel(avaliado: dict) -> bool:
    return not avaliado["erros"] and "reaproveitado_de" not in avaliado


def etapa_ragas(referencias: list[dict], saida: Path, geracao: Path, condicoes: list[str], sessao) -> int:
    from app.avaliacao.ragas_avaliacao import MODELO_JUIZ, EmbeddingsSerafim, JuizOllama, _pontuar, criar_metricas

    textos = referencias_anonimizadas(referencias, saida, sessao)
    por_id = {r["identificador"]: r for r in referencias}
    arquivo = saida / "ragas.jsonl"
    feitos = {(r["pergunta_id"], r["condicao"]): r for r in ler_jsonl(arquivo)}
    avaliados_por_entrada: dict[str, dict] = {}
    juiz = JuizOllama(settings.ollama_base_url, timeout=TEMPO_LIMITE_JUIZ, guardar_saidas=True)
    metricas = criar_metricas(juiz, EmbeddingsSerafim())
    total = 0
    with asyncio.Runner() as executor:
        for registro in ler_jsonl(geracao):
            referencia = por_id.get(registro["pergunta_id"])
            chave = (registro["pergunta_id"], registro["condicao"])
            if referencia is None or sem_evidencia(referencia) or registro["condicao"] not in condicoes:
                continue
            pergunta = referencia["enunciado"]
            entrada = entrada_ragas(pergunta, registro, textos[registro["pergunta_id"]])
            if chave in feitos:
                if reaproveitavel(feitos[chave]):
                    avaliados_por_entrada.setdefault(entrada, feitos[chave])
                continue
            original = avaliados_por_entrada.get(entrada)
            if original:
                anexar_jsonl(arquivo, {
                    **original, "condicao": registro["condicao"], "repeticao": registro["repeticao"],
                    "segundos": {}, "saidas_juiz": {}, "entrada_sha256": entrada,
                    "reaproveitado_de": original["condicao"],
                })
                total += 1
                print(registro["pergunta_id"], registro["condicao"], "reaproveitado de", original["condicao"], flush=True)
                continue
            chamadas = {}
            if not registro["abstencao"]:
                chamadas["faithfulness"] = dict(
                    user_input=pergunta, response=registro["texto"], retrieved_contexts=registro["contextos"]
                )
                chamadas["answer_relevancy"] = dict(user_input=pergunta, response=registro["texto"])
            if registro["contextos"]:
                base = dict(user_input=pergunta, reference=textos[registro["pergunta_id"]],
                            retrieved_contexts=registro["contextos"])
                chamadas["context_precision"] = base
                chamadas["context_recall"] = base
            valores, erros, segundos, saidas = dict.fromkeys(METRICAS_RAGAS), {}, {}, {}
            for nome, argumentos in chamadas.items():
                antes, inicio = len(juiz.saidas), time.monotonic()
                try:
                    valor, erro = executor.run(_pontuar(metricas[nome], **argumentos))
                except httpx.TimeoutException:
                    valor, erro = None, f"tempo esgotado ({TEMPO_LIMITE_JUIZ:.0f} s por chamada)"
                valores[nome] = valor
                segundos[nome] = round(time.monotonic() - inicio)
                saidas[nome] = juiz.saidas[antes:]
                if erro:
                    erros[nome] = erro
            avaliado = {
                "pergunta_id": registro["pergunta_id"], "condicao": registro["condicao"],
                "repeticao": registro["repeticao"], "modelo_juiz": MODELO_JUIZ, **valores,
                "erros": erros, "segundos": segundos, "saidas_juiz": saidas, "entrada_sha256": entrada,
            }
            anexar_jsonl(arquivo, avaliado)
            if reaproveitavel(avaliado):
                avaliados_por_entrada.setdefault(entrada, avaliado)
            total += 1
            print(registro["pergunta_id"], registro["condicao"], valores, erros or "", flush=True)
    return total


def _rankings(rastreio_recuperacao: dict, mapa: dict[str, str]) -> tuple[list[str], dict]:
    origem = origem_por_item(rastreio_recuperacao["fusao"], mapa)
    return ranking_logico(rastreio_recuperacao["ids_finais"], mapa), origem


def _curvas(recuperacao: list[dict], relevantes: dict[str, set[str]], mapa: dict[str, str]) -> list[dict]:
    linhas = []
    por_modo = defaultdict(list)
    for registro in recuperacao:
        if relevantes.get(registro["pergunta_id"]):
            por_modo[registro["modo"]].append(registro)
    for modo, registros in por_modo.items():
        for k in range(1, K_CURVA + 1):
            avaliacoes = [
                avaliar_ranking(
                    ranking_logico([f["item_id_canonico"] for f in r["rastreio"]["fusao"]], mapa),
                    relevantes[r["pergunta_id"]], k,
                )
                for r in registros
            ]
            linhas.append({"modo": modo, "k": k, **{c: v for c, v in agregar(avaliacoes).items()}})
    return linhas


def _variacao(geracoes: dict[int, list[dict]]) -> list[dict]:
    por_chave = defaultdict(dict)
    for repeticao, registros in geracoes.items():
        for r in registros:
            por_chave[(r["pergunta_id"], r["condicao"])][repeticao] = r
    linhas = []
    for (pergunta_id, condicao), reps in sorted(por_chave.items()):
        if len(reps) < 2:
            continue
        def iguais(funcao):
            return len({json.dumps(funcao(r), ensure_ascii=False) for r in reps.values()}) == 1
        linhas.append({
            "pergunta_id": pergunta_id, "condicao": condicao, "repeticoes": sorted(reps),
            "ranking_igual": iguais(lambda r: r["rastreio"]["recuperacao"]["ids_finais"]),
            "contexto_igual": iguais(lambda r: r["contextos"]),
            "saidas_brutas_iguais": iguais(
                lambda r: [c["saida_bruta"] for c in r["rastreio"]["chamadas_eventos"]]
                + [(r["rastreio"]["chamada_resposta"] or {}).get("saida_bruta")]
            ),
            "texto_igual": iguais(lambda r: r["texto"]),
            "fontes_iguais": iguais(lambda r: r["fontes"]),
            "abstencao_igual": iguais(lambda r: r["abstencao"]),
        })
    return linhas


def etapa_metricas(referencias: list[dict], saida: Path, sessao) -> dict:
    from app.avaliacao.itens import mapa_item_logico

    mapa = mapa_item_logico(sessao)
    relevantes, sem_id = {}, {}
    for referencia in referencias:
        relevantes[referencia["identificador"]], sem_id[referencia["identificador"]] = (
            relevantes_da_referencia(referencia, mapa)
        )
    pasta = saida / "metricas"
    pasta.mkdir(exist_ok=True)

    geracoes = {
        int(caminho.stem.removeprefix("geracao_r")): ler_jsonl(caminho)
        for caminho in sorted(saida.glob("geracao_r*.jsonl"))
    }
    por_pergunta, rankings = [], []
    resumo: dict = {"recuperacao_k5": {}, "geracao": {}, "consistencia": {}}
    for repeticao, registros in geracoes.items():
        avaliacoes = defaultdict(list)
        for registro in registros:
            pid, condicao = registro["pergunta_id"], registro["condicao"]
            ranking, origem = _rankings(registro["rastreio"]["recuperacao"], mapa)
            avaliacao = avaliar_ranking(ranking, relevantes[pid], K)
            fontes = ranking_logico(registro["fontes"], mapa)
            descartados = [
                d for c in registro["rastreio"]["chamadas_eventos"] for d in c["eventos_descartados"]
            ]
            situacoes = [c["situacao"] for c in registro["rastreio"]["chamadas_eventos"]]
            linha = {
                "pergunta_id": pid, "condicao": condicao, "repeticao": repeticao,
                "sem_evidencia": not relevantes[pid], "evidencias_sem_identificador": len(sem_id[pid]),
                **{c: avaliacao[c] for c in ("tp", "fp", "fn", "relevantes", "itens_na_lista", "precisao",
                                             "revocacao", "revocacao_maxima", "primeira_posicao_relevante",
                                             "rr", "ndcg")},
                "faltantes": " ".join(avaliacao["faltantes"]),
                "abstencao": registro["abstencao"], "fontes": len(fontes),
                "fontes_relevantes": sum(1 for f in fontes if f in relevantes[pid]),
                "eventos_descartados": len(descartados),
                "termos_descartados": " ".join(sorted({t for d in descartados for t in d["termos_sem_apoio"]})),
                "json_invalido": situacoes.count("json_invalido"),
                "abstencao_por_evidencia": situacoes.count("abstencao"),
                "truncada": registro["truncada"], "falhas_de_camada": " ".join(registro["rastreio"]["recuperacao"]["falhas"]),
                "segundos": registro["segundos"],
            }
            por_pergunta.append(linha)
            if relevantes[pid]:
                avaliacoes[condicao].append(avaliacao)
            if repeticao == 1:
                for item in linhas_do_ranking(ranking, relevantes[pid], origem):
                    rankings.append({"pergunta_id": pid, "condicao": condicao, **item})
                for item_id in avaliacao["faltantes"]:
                    rankings.append({"pergunta_id": pid, "condicao": condicao, "posicao": None,
                                     "item_id": item_id, "relevante": True, "ausente": True})
        resumo["recuperacao_k5"][f"r{repeticao}"] = {c: agregar(a) for c, a in avaliacoes.items()}
        da_repeticao = [linha for linha in por_pergunta if linha["repeticao"] == repeticao]
        resumo["geracao"][f"r{repeticao}"] = {
            condicao: _resumo_geracao([linha for linha in da_repeticao if linha["condicao"] == condicao])
            for condicao in CONDICOES
        }

    primeira = {(r["pergunta_id"], r["condicao"]): r for r in geracoes.get(1, [])}
    recuperacao = ler_jsonl(saida / "recuperacao.jsonl")
    so_recuperacao = {(r["pergunta_id"], r["modo"]): r for r in recuperacao}
    diferencas = []
    for (pid, condicao), registro in primeira.items():
        ids = registro["rastreio"]["recuperacao"]["ids_finais"]
        base = MESMA_RECUPERACAO.get(condicao, condicao)
        gemea = primeira.get((pid, base))
        if gemea and gemea["rastreio"]["recuperacao"]["ids_finais"] != ids:
            diferencas.append({"pergunta_id": pid, "condicao": condicao, "comparada_com": f"geracao/{base}"})
        avulsa = so_recuperacao.get((pid, base))
        if avulsa and [f["item_id_canonico"] for f in avulsa["rastreio"]["fusao"][:len(ids)]] != ids:
            diferencas.append({"pergunta_id": pid, "condicao": condicao, "comparada_com": f"recuperacao/{base}"})
    resumo["consistencia"] = {"rankings_diferentes": diferencas}

    curvas = _curvas(recuperacao, relevantes, mapa)
    resumo["recuperacao_so_busca_k5"] = {
        linha["modo"]: {c: v for c, v in linha.items() if c not in ("modo", "k")}
        for linha in curvas if linha["k"] == K
    }
    variacao = _variacao(geracoes)
    resumo["variacao_entre_repeticoes"] = {
        condicao: {
            campo: sum(1 for x in variacao if x["condicao"] == condicao and x[campo])
            for campo in ("ranking_igual", "contexto_igual", "saidas_brutas_iguais", "texto_igual", "fontes_iguais")
        } | {"pares": sum(1 for x in variacao if x["condicao"] == condicao)}
        for condicao in CONDICOES
    }

    ragas = ler_jsonl(saida / "ragas.jsonl")
    resumo["ragas_r1"] = {
        condicao: {
            metrica: _resumo_ragas([r for r in ragas if r["condicao"] == condicao], metrica)
            for metrica in METRICAS_RAGAS
        }
        for condicao in CONDICOES
    }

    k_ampliado = ler_jsonl(saida / "geracao_k_ampliado.jsonl")
    resumo["k_ampliado"] = [
        {
            "pergunta_id": r["pergunta_id"], "condicao": r["condicao"], "k": r["k"],
            **{c: v for c, v in avaliar_ranking(
                _rankings(r["rastreio"]["recuperacao"], mapa)[0], relevantes[r["pergunta_id"]], r["k"]
            ).items() if c in ("tp", "relevantes", "precisao", "revocacao", "itens_na_lista")},
            "fontes": len(r["fontes"]), "abstencao": r["abstencao"],
            "tokens_entrada": sum(c["tokens_entrada"] or 0 for c in r["rastreio"]["chamadas_eventos"]),
        }
        for r in k_ampliado
    ]

    _escrever_csv(pasta / "por_pergunta.csv", por_pergunta)
    _escrever_csv(pasta / "rankings_r1.csv", rankings)
    _escrever_csv(pasta / "curvas_por_k.csv", curvas)
    _escrever_csv(pasta / "variacao_entre_repeticoes.csv", variacao)
    (pasta / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumo


def _resumo_geracao(linhas: list[dict]) -> dict:
    return {
        "respostas": len(linhas),
        "abstencoes_com_evidencia": sum(1 for x in linhas if x["abstencao"] and not x["sem_evidencia"]),
        "abstencoes_sem_evidencia": sum(1 for x in linhas if x["abstencao"] and x["sem_evidencia"]),
        "perguntas_sem_evidencia": sum(1 for x in linhas if x["sem_evidencia"]),
        "eventos_descartados": sum(x["eventos_descartados"] for x in linhas),
        "json_invalido": sum(x["json_invalido"] for x in linhas),
        "truncadas": sum(1 for x in linhas if x["truncada"]),
    }


def _resumo_ragas(linhas: list[dict], metrica: str) -> dict:
    valores = [r[metrica] for r in linhas if r[metrica] is not None]
    return {
        "n": len(valores),
        "media": sum(valores) / len(valores) if valores else None,
        "erros": sum(1 for r in linhas if metrica in r["erros"]),
        "reaproveitados": sum(1 for r in linhas if r.get("reaproveitado_de") and r[metrica] is not None),
    }


def _escrever_csv(caminho: Path, linhas: list[dict]) -> None:
    if not linhas:
        caminho.write_text("", encoding="utf-8")
        return
    colunas = list(dict.fromkeys(c for linha in linhas for c in linha))
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({c: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                               for c, v in linha.items()})


def k_ampliado(referencias: list[dict], sessao) -> dict[str, int]:
    from app.avaliacao.itens import mapa_item_logico

    mapa = mapa_item_logico(sessao)
    tamanhos = {r["identificador"]: len(relevantes_da_referencia(r, mapa)[0]) for r in referencias}
    return {pid: min(total, K_CURVA) for pid, total in tamanhos.items() if total > K}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(description="Rodada de avaliação registrada contra uma referência validada.")
    parser.add_argument("etapa", choices=("recuperacao", "geracao", "k_ampliado", "ragas", "metricas"))
    parser.add_argument("--referencia", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--repeticao", type=int, default=1)
    parser.add_argument("--perguntas", default="")
    parser.add_argument("--condicoes", default=",".join(CONDICOES))
    argumentos = parser.parse_args(argv)

    from app.avaliacao.ragas_avaliacao import MODELO_JUIZ
    from app.geracao.llm import criar_cliente_llm

    saida = argumentos.saida
    saida.mkdir(parents=True, exist_ok=True)
    filtro = {p for p in argumentos.perguntas.split(",") if p}
    referencias = carregar_referencia(argumentos.referencia, filtro)
    condicoes = [c for c in argumentos.condicoes.split(",") if c]
    if set(condicoes) - set(CONDICOES):
        parser.error(f"condições desconhecidas: {sorted(set(condicoes) - set(CONDICOES))}")
    inicio = manifesto.agora()
    Sessao, qdrant, driver = _clientes()
    extras: dict = {"perguntas": len(referencias), "filtro_perguntas": sorted(filtro), "situacao": "interrompida"}
    try:
        with Sessao() as sessao:
            extras["ambiente"] = contexto_da_execucao(argumentos.referencia, sessao, qdrant, driver, MODELO_JUIZ)
            sessao.rollback()
            if argumentos.etapa == "recuperacao":
                extras["registros_novos"] = etapa_recuperacao(referencias, saida, sessao, qdrant, driver)
            elif argumentos.etapa == "geracao":
                arquivo = saida / f"geracao_r{argumentos.repeticao}.jsonl"
                extras |= {"repeticao": argumentos.repeticao, "condicoes": condicoes}
                extras["registros_novos"] = etapa_geracao(
                    referencias, saida, arquivo, argumentos.repeticao, condicoes, sessao, qdrant, driver,
                    criar_cliente_llm(),
                )
            elif argumentos.etapa == "k_ampliado":
                ks = k_ampliado(referencias, sessao)
                extras |= {"k_por_pergunta": ks, "condicoes": list(CONDICOES_K_AMPLIADO)}
                extras["registros_novos"] = etapa_geracao(
                    [r for r in referencias if r["identificador"] in ks], saida, saida / "geracao_k_ampliado.jsonl",
                    1, list(CONDICOES_K_AMPLIADO), sessao, qdrant, driver, criar_cliente_llm(), ks,
                )
            elif argumentos.etapa == "ragas":
                extras |= {"repeticao": 1, "condicoes": condicoes}
                extras["registros_novos"] = etapa_ragas(referencias, saida, saida / "geracao_r1.jsonl", condicoes, sessao)
            else:
                etapa_metricas(referencias, saida, sessao)
            extras["situacao"] = "concluida"
    except BaseException as erro:
        extras["erro"] = f"{type(erro).__name__}: {erro}"
        raise
    finally:
        registrar_etapa(saida, argumentos.etapa, inicio, extras)
        driver.close()
        qdrant.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
