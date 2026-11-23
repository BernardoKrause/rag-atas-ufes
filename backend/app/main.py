from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencias import criar_lifespan
from app.api.erros import registrar_tratadores
from app.api.rotas import roteador
from app.core.config import settings
from app.geracao.llm import ClienteLLM, criar_cliente_llm, modelos_instalados


def _fabrica_padrao(modelo: str | None) -> ClienteLLM:
    return criar_cliente_llm(modelo=modelo)


def criar_app(
    fabrica_llm: Callable[[str | None], ClienteLLM] = _fabrica_padrao,
    verificar_modelos: Callable[[], set[str] | None] = modelos_instalados,
) -> FastAPI:
    app = FastAPI(title="RAG Atas UFES", lifespan=criar_lifespan(fabrica_llm, verificar_modelos))
    registrar_tratadores(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origens,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(roteador)
    return app


app = criar_app()
