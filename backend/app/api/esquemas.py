from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.geracao.tipos import Resposta

Pergunta = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class PedidoConsulta(BaseModel):
    pergunta: Pergunta


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


def para_resposta_consulta(resposta: Resposta) -> RespostaConsulta:
    return RespostaConsulta(
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
