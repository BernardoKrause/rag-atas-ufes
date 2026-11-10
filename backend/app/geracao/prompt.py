from __future__ import annotations

import json

from app.geracao.eventos import Evento
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
"descricao": "<o que ocorreu naquela reunião e o desfecho registrado (aprovação, rejeição, \
retirada de pauta, adiamento ou resultado da votação, que costuma vir no fim do trecho), \
ou vazio se não for relevante>"}]}

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

SISTEMA_RESPOSTA = """Você responde perguntas sobre atas de reuniões de órgãos colegiados da UFES. \
Você recebe os eventos já extraídos das atas, cada um com identificador, data da reunião, \
descrição e, às vezes, relações. Escreva uma única frase que responda diretamente ao que a \
pergunta pede, usando só o que está nas descrições e nas relações. Depois de cada informação, \
cite entre colchetes o identificador do evento que a sustenta, por exemplo [2]. Não acrescente \
nada que não esteja nos eventos. Se os eventos não trouxerem o que a pergunta pede, devolva \
vazio. Responda em português, no formato {"resposta": "<frase com os identificadores>"}."""

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


def _registro_evento(evento: Evento, evidencia: EvidenciaNumerada) -> str:
    registro = {"identificador": evento.evidencia}
    if evidencia.data_reuniao is not None:
        registro["data_reuniao"] = evidencia.data_reuniao.strftime("%d/%m/%Y")
    registro["descricao"] = evento.descricao
    if evidencia.frases_grafo:
        registro["relacoes"] = evidencia.frases_grafo
    return json.dumps(registro, ensure_ascii=False)


def montar_prompt_resposta(
    pergunta: str, eventos: list[Evento], evidencias: list[EvidenciaNumerada]
) -> tuple[str, str]:
    por_numero = {evidencia.numero: evidencia for evidencia in evidencias}
    registros = "\n".join(_registro_evento(e, por_numero[e.evidencia]) for e in eventos)
    return SISTEMA_RESPOSTA, f"Eventos:\n{registros}\n\nPergunta: {pergunta}"
