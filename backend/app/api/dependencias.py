from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.geracao.llm import ClienteLLM
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant


def criar_lifespan(fabrica_llm: Callable[[], ClienteLLM]):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.cliente_llm = fabrica_llm()
        app.state.cliente_qdrant = _obter_cliente_qdrant()
        app.state.driver = obter_driver()
        engine = create_engine(settings.database_url)
        app.state.fabrica_sessao = sessionmaker(bind=engine)
        try:
            yield
        finally:
            app.state.driver.close()
            app.state.cliente_qdrant.close()
            engine.dispose()

    return lifespan


def obter_sessao(request: Request) -> Iterator[Session]:
    with request.app.state.fabrica_sessao() as sessao:
        yield sessao
