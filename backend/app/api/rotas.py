from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencias import obter_sessao
from app.api.esquemas import (
    ModeloSaida,
    ModelosSaida,
    OrgaoSaida,
    PedidoConsulta,
    RespostaConsulta,
    para_resposta_consulta,
)
from app.api.numeros import ocultar_numeros, revelar_na_resposta
from app.api.registro import registrar_consulta
from app.core.config import settings
from app.geracao.llm import ClienteLLM, modelos_permitidos, parametros_geracao
from app.geracao.respondedor import responder
from app.geracao.tipos import ErroGeracao
from app.recuperacao.setor import NOMES_POR_EXTENSO, identificar_orgao, listar_orgaos
from app.ingestion.collector import path_seguro
from app.models.documento import Documento

roteador = APIRouter()


@roteador.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@roteador.get("/orgaos", response_model=list[OrgaoSaida])
def orgaos(sessao: Session = Depends(obter_sessao)) -> list[OrgaoSaida]:
    return [
        OrgaoSaida(sigla=sigla, nome=NOMES_POR_EXTENSO.get(sigla), atas=total)
        for sigla, total in listar_orgaos(sessao)
    ]


@roteador.get("/modelos", response_model=ModelosSaida)
def modelos(request: Request) -> ModelosSaida:
    permitidos = modelos_permitidos()
    if settings.llm_provedor.strip().lower() != "ollama":
        disponiveis = set(permitidos)
    else:
        disponiveis = _instalados(request) or set()
    return ModelosSaida(
        padrao=settings.llm_modelo.strip(),
        modelos=[ModeloSaida(nome=nome, disponivel=nome in disponiveis) for nome in permitidos],
    )


@roteador.post("/consultas", response_model=RespostaConsulta)
def consultar(
    pedido: PedidoConsulta, request: Request, sessao: Session = Depends(obter_sessao)
) -> RespostaConsulta:
    estado = request.app.state
    orgao = pedido.orgao or None
    if orgao is not None and orgao not in {sigla for sigla, _ in listar_orgaos(sessao)}:
        raise HTTPException(status_code=422, detail="Órgão não encontrado no acervo.")
    modelo = pedido.modelo or settings.llm_modelo.strip()
    cliente = _cliente_do_modelo(request, modelo)
    pergunta = ocultar_numeros(pedido.pergunta, sessao)
    resposta = responder(pergunta, sessao, estado.cliente_qdrant, estado.driver, cliente, orgao=orgao)
    orgao_usado = orgao or identificar_orgao(pergunta, sessao)
    configuracao = {
        **parametros_geracao(modelo),
        "orgao": orgao_usado,
        "escopo": "selecao" if orgao else ("pergunta" if orgao_usado else "acervo"),
    }
    registrar_consulta(settings.consultas_registro, pergunta, configuracao, resposta)
    return para_resposta_consulta(revelar_na_resposta(resposta, sessao), configuracao)


def _instalados(request: Request) -> set[str] | None:
    return request.app.state.verificar_modelos()


def _cliente_do_modelo(request: Request, modelo: str) -> ClienteLLM:
    estado = request.app.state
    if modelo == settings.llm_modelo.strip():
        return estado.cliente_llm
    if modelo not in modelos_permitidos():
        raise HTTPException(status_code=422, detail="Modelo não disponível neste ambiente.")
    instalados = _instalados(request)
    if instalados is None:
        raise ErroGeracao("não foi possível consultar os modelos instalados no Ollama")
    if modelo not in instalados:
        raise HTTPException(status_code=422, detail="Modelo não instalado no Ollama.")
    if modelo not in estado.clientes_llm:
        estado.clientes_llm[modelo] = estado.fabrica_llm(modelo)
    return estado.clientes_llm[modelo]


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
