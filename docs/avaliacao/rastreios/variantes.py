import copy, json, sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.geracao.prompt as pr
from app.core.config import settings
from app.geracao.contexto import montar_contexto
from app.geracao.eventos import interpretar_eventos, montar_texto
from app.geracao.llm import criar_cliente_llm
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant
from app.recuperacao.orquestrador import recuperar

BASE_SIS, BASE_ESQ = pr.SISTEMA, copy.deepcopy(pr.ESQUEMA_EVENTOS)

def variante(nome):
    sis, esq = BASE_SIS, copy.deepcopy(BASE_ESQ)
    itens = esq["properties"]["eventos"]["items"]
    if nome in ("V1", "V3", "V4"):
        sis = sis.replace('"resposta": "<resposta direta ao que a pergunta pede, ou vazio>", ', '')
        del itens["properties"]["resposta"]; itens["required"].remove("resposta")
    if nome == "V3":
        sis = sis.replace('"descricao": "<o que ocorreu naquela reunião, com a decisão', '"descricao": "<o que ocorreu naquela reunião, respondendo ao que a pergunta pede, com a decisão')
    if nome == "V4":
        sis = sis.replace('or do resultado da votação \nregistrado, ou vazio se não for relevante>"}]}', 'X')
        sis = sis.replace('ou vazio se não for relevante>"}]}', 'ou vazio se não for relevante>"}], "resposta_direta": "<depois de avaliar todas as evidências, a resposta direta ao que a pergunta pede, em uma frase, ou vazio>"}')
        esq["properties"]["resposta_direta"] = {"type": "string"}
        esq["required"] = ["eventos", "resposta_direta"]
    if nome == "V2":
        sis = sis.replace('{"evidencia": <identificador>, "relevante": true|false, "resposta": "<resposta direta ao que a pergunta pede, ou vazio>", "descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação registrado, ou vazio se não for relevante>"}',
                          '{"evidencia": <identificador>, "descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação registrado>", "resposta": "<resposta direta ao que a pergunta pede, ou vazio>", "relevante": true|false}')
        props = itens["properties"]
        itens["properties"] = {k: props[k] for k in ("evidencia", "descricao", "resposta", "relevante")}
    assert nome == "V0" or sis != BASE_SIS, "substituição não aplicada"
    return sis, esq

def dcc():
    from datetime import date
    from app.geracao.tipos import EvidenciaNumerada, Fonte
    def ev(n, texto, frases, ant=None, post=None):
        return EvidenciaNumerada(n, Fonte(n, f"e{n}", 1, "Ata CT, 7ª reunião ordinária, 01/01/2025, pauta, item %d" % n, texto, None), texto, frases, ant, post, date(2025, 1, 1))
    fr = ["Centro: CT.", "Departamento: DCC.", "Data da reunião: 2025-01-01."]
    return [ev(1, "O conselho aprovou por unanimidade a criação da disciplina optativa Aprendizado de Máquina Aplicado, com 60 horas.", fr + ["Desfecho: Aprovado.", "Resultado da votação: unanimidade."], "Aprovação de ata", "Informes"),
            ev(2, "Aprovação da ata da reunião anterior.", fr, None, "Criação de disciplina optativa"),
            ev(3, "Informes gerais da chefia sobre o calendário.", fr, "Criação de disciplina optativa", None)]


s = sessionmaker(bind=create_engine(settings.database_url))(); q = _obter_cliente_qdrant(); d = obter_driver(); llm = criar_cliente_llm()
perguntas = json.load(open(sys.argv[1]))
for nome in sys.argv[2].split(","):
    sis, esq = variante(nome)
    for rotulo, p in perguntas.items():
        numeradas = dcc() if rotulo == "DCC" else montar_contexto(recuperar(p, s, q, d), s)
        _, usuario = pr.montar_prompt(p, numeradas)
        bruta = llm.gerar(sis, usuario, esquema=esq)
        datas = {e.numero: e.data_reuniao for e in numeradas}
        ev = interpretar_eventos(bruta.texto, datas)
        print(f"--- {nome} {rotulo} ({bruta.tokens_saida} tok)")
        print(montar_texto(ev, datas) if ev else f"ABSTENÇÃO / bruta: {bruta.texto[:300]}")
        if nome == "V4":
            print("  resposta_direta:", json.loads(bruta.texto).get("resposta_direta"))
