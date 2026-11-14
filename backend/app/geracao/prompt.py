from __future__ import annotations

import json

from app.geracao.tipos import EvidenciaNumerada

FRASE_ABSTENCAO = (
    "Não encontrei nas atas disponíveis informação suficiente para responder a essa "
    "pergunta."
)

SISTEMA = """Você responde perguntas sobre atas de reuniões de órgãos colegiados da UFES \
usando exclusivamente as evidências fornecidas.

Cada evidência é um registro separado, com identificador, data da reunião, fonte e trecho. \
Os campos de item anterior e posterior servem apenas de contexto.

Avalie cada evidência separadamente, na ordem em que aparecem, e devolva um registro \
para cada uma, em JSON. Uma evidência é relevante se registra algo sobre o assunto da \
pergunta, mesmo que seja curta (por exemplo, retirada de pauta ou adiamento). Uma \
evidência que não trata do assunto da pergunta não é relevante e não deve ser descrita \
só para dizer que não traz a informação.

Formato: {"eventos": [{"evidencia": <identificador>, "relevante": true|false, \
"descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação \
registrado, ou vazio se não for relevante>"}]}

Use apenas as evidências. Descreva só o que o registro traz, no trecho e nas relações, \
sem inferir motivos, consequências ou ligações com outras reuniões. Responda em português."""

ESQUEMA_EVENTOS = {
    "type": "object",
    "properties": {
        "eventos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidencia": {"type": "integer"},
                    "relevante": {"type": "boolean"},
                    "descricao": {"type": "string"},
                },
                "required": ["evidencia", "relevante", "descricao"],
            },
        }
    },
    "required": ["eventos"],
}

SISTEMA_RESPOSTA = """Você responde perguntas sobre atas de reuniões de órgãos colegiados da UFES \
usando exclusivamente as evidências fornecidas. Escreva uma única frase que responda \
diretamente ao que a pergunta pede, usando o trecho e as relações das evidências. \
Não invente. Se as evidências não trouxerem o que a pergunta pede, devolva vazio. \
Responda em português, no formato {"resposta": "<frase>"}."""

ESQUEMA_RESPOSTA = {
    "type": "object",
    "properties": {"resposta": {"type": "string"}},
    "required": ["resposta"],
}


def _registro(evidencia: EvidenciaNumerada) -> str:
    registro = {"identificador": evidencia.numero}
    if evidencia.data_reuniao is not None:
        registro["data_reuniao"] = evidencia.data_reuniao.strftime("%d/%m/%Y")
    registro["fonte"] = evidencia.fonte.rotulo
    registro["trecho"] = evidencia.texto
    if evidencia.frases_grafo:
        registro["relacoes"] = evidencia.frases_grafo
    if evidencia.assunto_anterior:
        registro["item_anterior_nao_citavel"] = evidencia.assunto_anterior
    if evidencia.assunto_posterior:
        registro["item_posterior_nao_citavel"] = evidencia.assunto_posterior
    return json.dumps(registro, ensure_ascii=False)


def montar_prompt(
    pergunta: str, evidencias: list[EvidenciaNumerada]
) -> tuple[str, str]:
    registros = "\n".join(_registro(evidencia) for evidencia in evidencias)
    return SISTEMA, f"Evidências:\n{registros}\n\nPergunta: {pergunta}"
