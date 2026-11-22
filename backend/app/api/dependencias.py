from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.geracao.llm import ClienteLLM
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant, carregar_modelo


def criar_lifespan(
    fabrica_llm: Callable[[str | None], ClienteLLM],
    verificar_modelos: Callable[[], set[str] | None],
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.fabrica_llm = fabrica_llm
        app.state.verificar_modelos = verificar_modelos
        app.state.cliente_llm = fabrica_llm(None)
        app.state.clientes_llm = {}
        with ExitStack() as pilha:
            app.state.cliente_qdrant = _obter_cliente_qdrant()
            pilha.callback(app.state.cliente_qdrant.close)
            app.state.driver = obter_driver()
            pilha.callback(app.state.driver.close)
            engine = create_engine(settings.database_url)
            pilha.callback(engine.dispose)
            app.state.fabrica_sessao = sessionmaker(bind=engine)
            carregar_modelo()
            yield

    return lifespan


def obter_sessao(request: Request) -> Iterator[Session]:
    with request.app.state.fabrica_sessao() as sessao:
        yield sessao
