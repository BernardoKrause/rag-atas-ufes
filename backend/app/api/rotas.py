from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencias import obter_sessao
from app.api.esquemas import PedidoConsulta, RespostaConsulta, para_resposta_consulta
from app.geracao.respondedor import responder

roteador = APIRouter()


@roteador.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@roteador.post("/consultas", response_model=RespostaConsulta)
def consultar(
    pedido: PedidoConsulta, request: Request, sessao: Session = Depends(obter_sessao)
) -> RespostaConsulta:
    estado = request.app.state
    resposta = responder(
        pedido.pergunta, sessao, estado.cliente_qdrant, estado.driver, estado.cliente_llm
    )
    return para_resposta_consulta(resposta)
