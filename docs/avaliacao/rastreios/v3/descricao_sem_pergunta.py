import csv
import json
import sys
import time
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.geracao.contexto import montar_contexto
from app.geracao.eventos import (
    Evento,
    desfecho_registrado,
    interpretar_eventos,
    ler_resposta_direta,
    montar_texto,
)
from app.geracao.llm import criar_cliente_llm
from app.geracao.prompt import ESQUEMA_EVENTOS, ESQUEMA_RESPOSTA, montar_prompt, montar_prompt_resposta
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant
from app.recuperacao.orquestrador import recuperar

PERGUNTAS = "/Users/bk/Documents/Projects/RAG ATAS UFES - TCC/deploy_bernardo/amostra_personas_40/perguntas.csv"

SISTEMA_DESCRICAO = """Você descreve um registro de ata de reunião de órgão colegiado da UFES.

Escreva uma descrição curta do que o registro traz: o assunto, com os nomes de órgãos, \
departamentos, cursos, semestres, números e pessoas exatamente como aparecem no trecho, e o \
desfecho registrado (aprovação, rejeição, retirada de pauta, adiamento ou resultado da \
votação, que costuma vir no fim do trecho). Se o trecho tratar de vários assuntos, descreva \
cada um numa frase. Use só o trecho e as relações, sem inferir motivos, consequências ou \
ligações com outras reuniões. Responda em português, no formato {"descricao": "<texto>"}."""

ESQUEMA_DESCRICAO = {
    "type": "object",
    "properties": {"descricao": {"type": "string"}},
    "required": ["descricao"],
}

CRITERIO_ATUAL = """Uma evidência é relevante se registra algo sobre o assunto da pergunta, \
mesmo que seja curta (por exemplo, retirada de pauta ou adiamento). Uma evidência que não \
trata do assunto da pergunta não é relevante."""

CRITERIO_ESTRITO = CRITERIO_ATUAL + """ Quando a pergunta especifica órgão, departamento, \
curso, semestre, número de processo, projeto ou pessoa, a evidência só é relevante se tratar \
desse mesmo órgão, departamento, curso, semestre, processo, projeto ou pessoa. Um registro \
de assunto parecido sobre outro departamento, outro semestre ou outra pessoa não é relevante."""

ESQUEMA_RELEVANCIA = {
    "type": "object",
    "properties": {"relevante": {"type": "boolean"}},
    "required": ["relevante"],
}

ESQUEMA_RELEVANTES = {
    "type": "object",
    "properties": {"relevantes": {"type": "array", "items": {"type": "integer"}}},
    "required": ["relevantes"],
}


def sistema_relevancia(criterio):
    return f"""Você decide se um registro de ata de reunião de órgão colegiado da UFES é \
relevante para uma pergunta. Você recebe a pergunta, o trecho do registro e uma descrição \
dele. {criterio} Responda no formato {{"relevante": true|false}}."""


def sistema_relevantes(criterio):
    return f"""Você decide quais registros de atas de reuniões de órgãos colegiados da UFES \
são relevantes para uma pergunta. Você recebe a pergunta e os registros, cada um com \
identificador, data, fonte e descrição. Avalie cada registro. {criterio} Responda no formato \
{{"relevantes": [<identificadores dos registros relevantes>]}}."""


def registro_cego(e):
    r = {"data_reuniao": e.data_reuniao.strftime("%d/%m/%Y") if e.data_reuniao else None,
         "fonte": e.fonte.rotulo, "trecho": e.texto}
    if e.frases_grafo:
        r["relacoes"] = e.frases_grafo
    return json.dumps(r, ensure_ascii=False)


def campo(texto, nome, padrao):
    try:
        return json.loads(texto[texto.find("{"):]).get(nome, padrao)
    except (json.JSONDecodeError, ValueError, AttributeError):
        return padrao


def final(llm, pergunta, eventos, numeradas, datas):
    if not eventos:
        return "(abstenção)", []
    eventos = sorted(eventos, key=lambda ev: datas[ev.evidencia])
    s, u = montar_prompt_resposta(pergunta, eventos, numeradas)
    direta = ler_resposta_direta(llm.gerar(s, u, esquema=ESQUEMA_RESPOSTA).texto, eventos)
    desfechos = {e.numero: desfecho_registrado(e.frases_grafo) for e in numeradas}
    return montar_texto(eventos, datas, direta, desfechos), [ev.evidencia for ev in eventos]


def main():
    perguntas = {r["n"]: r["pergunta"] for r in csv.DictReader(open(PERGUNTAS, encoding="utf-8-sig"), delimiter=";")}
    sessao = sessionmaker(bind=create_engine(settings.database_url))()
    qd, drv, llm = _obter_cliente_qdrant(), obter_driver(), criar_cliente_llm()
    for n in sys.argv[1:]:
        q = perguntas[n]
        numeradas = montar_contexto(recuperar(q, sessao, qd, drv), sessao)
        datas = {e.numero: e.data_reuniao or date.min for e in numeradas}
        por_numero = {e.numero: e for e in numeradas}
        r = {"n": n, "pergunta": q,
             "contexto": [{"n": e.numero, "rotulo": e.fonte.rotulo, "trecho": e.texto} for e in numeradas],
             "variantes": {}, "segundos": {}}

        t = time.time()
        eventos = []
        for e in numeradas:
            s, u = montar_prompt(q, [e])
            eventos += interpretar_eventos(llm.gerar(s, u, esquema=ESQUEMA_EVENTOS).texto, {e.numero: datas[e.numero]}) or []
        texto, cit = final(llm, q, eventos, numeradas, datas)
        r["variantes"]["atual"] = {"descricoes": {ev.evidencia: ev.descricao for ev in eventos}, "texto": texto}
        r["segundos"]["atual"] = round(time.time() - t)

        t = time.time()
        cegas = {e.numero: campo(llm.gerar(SISTEMA_DESCRICAO, registro_cego(e), esquema=ESQUEMA_DESCRICAO).texto, "descricao", "").strip()
                 for e in numeradas}
        r["descricoes_cegas"] = cegas
        r["segundos"]["descricao_cega"] = round(time.time() - t)

        for nome, criterio in (("A_por_evidencia", CRITERIO_ATUAL), ("A_estrito", CRITERIO_ESTRITO)):
            t = time.time()
            relevantes = []
            for e in numeradas:
                u = json.dumps({"pergunta": q, "trecho": e.texto, "descricao": cegas[e.numero]}, ensure_ascii=False)
                if campo(llm.gerar(sistema_relevancia(criterio), u, esquema=ESQUEMA_RELEVANCIA).texto, "relevante", False) is True:
                    relevantes.append(e.numero)
            evs = [Evento(k, cegas[k]) for k in relevantes if cegas[k]]
            texto, cit = final(llm, q, evs, numeradas, datas)
            r["variantes"][nome] = {"relevantes": relevantes, "texto": texto}
            r["segundos"][nome] = round(time.time() - t)

        for nome, criterio in (("B_conjunta", CRITERIO_ATUAL), ("B_estrito", CRITERIO_ESTRITO)):
            t = time.time()
            registros = "\n".join(json.dumps({"identificador": e.numero, "data_reuniao": e.data_reuniao.strftime("%d/%m/%Y") if e.data_reuniao else None,
                                              "fonte": e.fonte.rotulo, "descricao": cegas[e.numero]}, ensure_ascii=False) for e in numeradas)
            ids = campo(llm.gerar(sistema_relevantes(criterio), f"Registros:\n{registros}\n\nPergunta: {q}", esquema=ESQUEMA_RELEVANTES).texto, "relevantes", [])
            relevantes = sorted({i for i in ids if isinstance(i, int) and i in por_numero})
            evs = [Evento(k, cegas[k]) for k in relevantes if cegas[k]]
            texto, cit = final(llm, q, evs, numeradas, datas)
            r["variantes"][nome] = {"relevantes": relevantes, "texto": texto}
            r["segundos"][nome] = round(time.time() - t)

        print(json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
