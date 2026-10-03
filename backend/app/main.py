from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencias import criar_lifespan
from app.api.erros import registrar_tratadores
from app.api.rotas import roteador
from app.core.config import settings
from app.geracao.llm import ClienteLLM, criar_cliente_llm


def criar_app(fabrica_llm: Callable[[], ClienteLLM] = criar_cliente_llm) -> FastAPI:
    app = FastAPI(title="RAG Atas UFES", lifespan=criar_lifespan(fabrica_llm))
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
