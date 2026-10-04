from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencias import obter_sessao
from app.api.esquemas import PedidoConsulta, RespostaConsulta, para_resposta_consulta
from app.geracao.respondedor import responder
from app.ingestion.collector import path_seguro
from app.models.documento import Documento

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


@roteador.get("/documentos/{id_documento}/pdf")
def baixar_pdf(id_documento: int, sessao: Session = Depends(obter_sessao)) -> FileResponse:
    documento = sessao.get(Documento, id_documento)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    caminho = path_seguro(Path(documento.url_origem))
    if not caminho.is_file():
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return FileResponse(
        caminho,
        media_type="application/pdf",
        filename=documento.nome_arquivo,
        content_disposition_type="inline",
    )
