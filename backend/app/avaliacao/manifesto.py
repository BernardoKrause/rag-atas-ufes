from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path

import httpx
from sqlalchemy import text

from app.core.config import REPO_ROOT, settings
from app.geracao.prompt import SISTEMA, SISTEMA_RESPOSTA
from app.recuperacao.fusao import PROFUNDIDADE_FUSAO, RRF_K
from app.recuperacao.orquestrador import K_PADRAO, TOP_N_ANCORA_PADRAO
from app.recuperacao.tipos import LIMITE_PADRAO

PACOTES = (
    "ragas", "qdrant-client", "neo4j", "sqlalchemy", "torch", "transformers", "httpx", "pydantic",
)


def agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_arquivo(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def sha256_texto(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _git(*argumentos: str) -> str:
    return subprocess.run(
        ["git", *argumentos], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()


def versao_do_codigo() -> dict:
    alteracoes = [linha for linha in _git("status", "--porcelain").splitlines() if linha]
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "alteracoes_nao_commitadas": [linha for linha in alteracoes if not linha.startswith("??")],
        "arquivos_nao_rastreados": [linha[3:] for linha in alteracoes if linha.startswith("??")],
    }


def versao_dos_dados(sessao, cliente_qdrant, driver) -> dict:
    linhas = sessao.execute(
        text("select item_id_canonico, md5(texto) from itens_pauta order by item_id_canonico")
    ).all()
    impressao = sha256_texto("\n".join(f"{item_id}\t{md5}" for item_id, md5 in linhas))
    documentos = sessao.execute(text("select count(*) from documentos")).scalar_one()
    colecao = cliente_qdrant.get_collection(settings.qdrant_collection)
    with driver.session() as sessao_grafo:
        nos = {r["rotulo"]: r["total"] for r in sessao_grafo.run(
            "MATCH (n) RETURN labels(n)[0] AS rotulo, count(*) AS total ORDER BY rotulo"
        )}
        relacoes = {r["tipo"]: r["total"] for r in sessao_grafo.run(
            "MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS total ORDER BY tipo"
        )}
    return {
        "postgres": {"documentos": documentos, "itens_pauta": len(linhas), "impressao_itens_sha256": impressao},
        "qdrant": {"colecao": settings.qdrant_collection, "pontos": colecao.points_count},
        "neo4j": {"nos": nos, "relacoes": relacoes},
    }


def _digest(modelos: list[dict], nome: str) -> str | None:
    return next((m.get("digest") for m in modelos if m.get("name") == nome or m.get("model") == nome), None)


def _revisao_hf(nome: str) -> str | None:
    referencia = Path.home() / ".cache/huggingface/hub" / f"models--{nome.replace('/', '--')}" / "refs/main"
    return referencia.read_text().strip() if referencia.exists() else None


def versao_dos_modelos(modelo_juiz: str) -> dict:
    from app.ingestion.indexador import NOME_MODELO

    try:
        with httpx.Client(base_url=settings.ollama_base_url, timeout=30) as cliente:
            versao = cliente.get("/api/version").json().get("version")
            modelos = cliente.get("/api/tags").json().get("models", [])
    except httpx.HTTPError as erro:
        versao, modelos = f"indisponível: {erro}", []
    return {
        "ollama": versao,
        "gerador": {"nome": settings.llm_modelo, "provedor": settings.llm_provedor,
                    "digest": _digest(modelos, settings.llm_modelo)},
        "juiz": {"nome": modelo_juiz, "digest": _digest(modelos, modelo_juiz)},
        "embeddings": {"nome": NOME_MODELO, "revisao_hf": _revisao_hf(NOME_MODELO)},
    }


def parametros() -> dict:
    return {
        "k": K_PADRAO,
        "top_n_ancora": TOP_N_ANCORA_PADRAO,
        "rrf_k": RRF_K,
        "profundidade_fusao": PROFUNDIDADE_FUSAO,
        "candidatos_por_busca": LIMITE_PADRAO,
        "llm_temperatura": 0,
        "llm_seed": None,
        "llm_num_ctx": settings.llm_num_ctx,
        "llm_max_tokens": settings.llm_max_tokens,
        "llm_timeout_s": settings.llm_timeout,
        "prompt_eventos_sha256": sha256_texto(SISTEMA),
        "prompt_resposta_sha256": sha256_texto(SISTEMA_RESPOSTA),
    }


def ambiente() -> dict:
    pacotes = {}
    for nome in PACOTES:
        try:
            pacotes[nome] = metadata.version(nome)
        except metadata.PackageNotFoundError:
            pacotes[nome] = None
    return {"python": sys.version.split()[0], "plataforma": platform.platform(), "pacotes": pacotes}
