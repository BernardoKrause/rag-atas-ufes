from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.geracao.tipos import ErroGeracao

logger = logging.getLogger(__name__)


async def _erro_geracao(request: Request, erro: ErroGeracao) -> JSONResponse:
    logger.error("falha na geração: %s", erro, exc_info=erro)
    return JSONResponse(
        status_code=503,
        content={"detail": "Serviço de geração indisponível. Tente novamente."},
    )


async def _capturar_erro_inesperado(request: Request, chamar_proximo):
    try:
        return await chamar_proximo(request)
    except Exception as erro:
        logger.error("erro inesperado: %s", erro, exc_info=erro)
        return JSONResponse(status_code=500, content={"detail": "Erro interno."})


def registrar_tratadores(app: FastAPI) -> None:
    app.add_exception_handler(ErroGeracao, _erro_geracao)
    app.middleware("http")(_capturar_erro_inesperado)
