import copy, json, sys
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.geracao.prompt as pr
import app.geracao.respondedor as rp
from app.core.config import settings
from app.geracao.contexto import montar_contexto
from app.geracao.llm import criar_cliente_llm
from app.geracao.tipos import EvidenciaNumerada, Fonte
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant
from app.recuperacao.orquestrador import recuperar

BASE_SIS, BASE_ESQ = pr.SISTEMA, copy.deepcopy(pr.ESQUEMA_EVENTOS)
FORMATO_A0 = '''Formato: {"eventos": [{"evidencia": <identificador>, "relevante": true|false, \
"descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação \
registrado, ou vazio se não for relevante>"}]}'''


def variante(nome):
    sis, esq = BASE_SIS, copy.deepcopy(BASE_ESQ)
    itens = esq["properties"]["eventos"]["items"]
    if nome == "A1":
        sis = sis.replace(
            "Avalie cada evidência separadamente, na ordem em que aparecem, e devolva um registro \
para cada uma, em JSON.",
            "Avalie cada evidência separadamente, na ordem em que aparecem, e devolva um registro \
para cada uma, em JSON: primeiro descreva o que o trecho registra e só depois diga se é relevante.")
        sis = sis.replace(
            " Uma \
evidência que não trata do assunto da pergunta não é relevante e não deve ser descrita \
só para dizer que não traz a informação.",
            " Uma \
evidência que não trata do assunto da pergunta não é relevante.")
        sis = sis.replace(FORMATO_A0, '''Formato: {"eventos": [{"evidencia": <identificador>, \
"descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação registrado>", \
"relevante": true|false}]}''')
        props = itens["properties"]
        itens["properties"] = {k: props[k] for k in ("evidencia", "descricao", "relevante")}
        itens["required"] = ["evidencia", "descricao", "relevante"]
    assert nome == "A0" or sis.count("só depois") == 1 and FORMATO_A0 not in sis, "substituição não aplicada"
    return sis, esq


def dcc(*_a, **_k):
    def ev(n, texto, frases, ant=None, post=None):
        return EvidenciaNumerada(n, Fonte(n, f"e{n}", 1, "Ata CT, 7ª reunião ordinária, 01/01/2025, pauta, item %d" % n, texto, None), texto, frases, ant, post, date(2025, 1, 1))
    fr = ["Centro: CT.", "Departamento: DCC.", "Data da reunião: 2025-01-01."]
    return [ev(1, "O conselho aprovou por unanimidade a criação da disciplina optativa Aprendizado de Máquina Aplicado, com 60 horas.", fr + ["Desfecho: Aprovado.", "Resultado da votação: unanimidade."], "Aprovação de ata", "Informes"),
            ev(2, "Aprovação da ata da reunião anterior.", fr, None, "Criação de disciplina optativa"),
            ev(3, "Informes gerais da chefia sobre o calendário.", fr, "Criação de disciplina optativa", None)]


if __name__ == "__main__":
    s = sessionmaker(bind=create_engine(settings.database_url))(); q = _obter_cliente_qdrant(); d = obter_driver(); llm = criar_cliente_llm()
    perguntas = json.load(open(sys.argv[1]))
    for nome in sys.argv[2].split(","):
        sis, esq = variante(nome)
        pr.SISTEMA = sis
        rp.ESQUEMA_EVENTOS = esq
        for rotulo, p in perguntas.items():
            if rotulo == "DCC":
                rp.recuperar, rp.montar_contexto = (lambda *a, **k: [1]), dcc
            else:
                rp.recuperar, rp.montar_contexto = recuperar, montar_contexto
            det = rp.responder_detalhado(p, s, q, d, llm)
            print(f"--- {nome} {rotulo} ({det.saida_llm.tokens_saida if det.saida_llm else '-'} tok) contexto={len(det.evidencias)}")
            print(det.resposta.texto)
            if det.saida_llm:
                nao = [e for e in json.loads(det.saida_llm.texto[det.saida_llm.texto.find('{'):]).get("eventos", []) if e.get("relevante") is not True]
                print("  irrelevantes:", [(e.get("evidencia"), (e.get("descricao") or "")[:90]) for e in nao])
            sys.stdout.flush()
