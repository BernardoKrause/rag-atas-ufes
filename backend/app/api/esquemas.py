from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.geracao.tipos import Resposta

Pergunta = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Opcao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class PedidoConsulta(BaseModel):
    pergunta: Pergunta
    orgao: Opcao | None = None
    modelo: Opcao | None = None


class ConfiguracaoSaida(BaseModel):
    provedor: str
    modelo: str
    max_tokens: int
    temperatura: float | None = None
    num_ctx: int | None = None
    orgao: str | None
    escopo: str


class OrgaoSaida(BaseModel):
    sigla: str
    nome: str | None
    atas: int


class ModeloSaida(BaseModel):
    nome: str
    disponivel: bool


class ModelosSaida(BaseModel):
    padrao: str
    modelos: list[ModeloSaida]


class FonteSaida(BaseModel):
    numero: int
    item_id_canonico: str
    rotulo: str
    trecho: str
    pagina: int | None
    url_pdf: str


class RespostaConsulta(BaseModel):
    texto: str
    abstencao: bool
    fontes: list[FonteSaida]
    configuracao: ConfiguracaoSaida


def para_resposta_consulta(resposta: Resposta, configuracao: dict) -> RespostaConsulta:
    return RespostaConsulta(
        configuracao=ConfiguracaoSaida(**configuracao),
        texto=resposta.texto,
        abstencao=resposta.abstencao,
        fontes=[
            FonteSaida(
                numero=fonte.numero,
                item_id_canonico=fonte.item_id_canonico,
                rotulo=fonte.rotulo,
                trecho=fonte.trecho,
                pagina=fonte.pagina,
                url_pdf=f"/documentos/{fonte.documento_id}/pdf",
            )
            for fonte in resposta.fontes
        ],
    )
