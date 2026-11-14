import csv, json, sys
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.recuperacao.orquestrador as orq
from app.core.config import settings
from app.geracao.contexto import montar_contexto
from app.geracao.eventos import interpretar_eventos
from app.geracao.llm import criar_cliente_llm
from app.geracao.prompt import ESQUEMA_EVENTOS, montar_prompt
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant

P = "/Users/bk/Documents/Projects/RAG ATAS UFES - TCC/deploy_bernardo/amostra_personas_40/perguntas.csv"
perguntas = {r["n"]: r["pergunta"] for r in csv.DictReader(open(P, encoding="utf-8-sig"), delimiter=";")}
sessao = sessionmaker(bind=create_engine(settings.database_url))()
qd, drv, llm = _obter_cliente_qdrant(), obter_driver(), criar_cliente_llm()
original = orq.identificar_orgao
saida = []
for n in sys.argv[1:]:
    q = perguntas[n]
    for filtro in (False, True):
        orq.identificar_orgao = original if filtro else (lambda *a, **k: None)
        numeradas = montar_contexto(orq.recuperar(q, sessao, qd, drv), sessao)
        datas = {e.numero: e.data_reuniao or date.min for e in numeradas}
        ctx = [{"n": e.numero, "rotulo": e.fonte.rotulo, "item": e.fonte.item_id_canonico, "inicio": e.texto[:160]} for e in numeradas]
        por_ev = {}
        for e in numeradas:
            s, u = montar_prompt(q, [e])
            ev = interpretar_eventos(llm.gerar(s, u, esquema=ESQUEMA_EVENTOS).texto, {e.numero: datas[e.numero]}) or []
            por_ev[e.numero] = [x.descricao for x in ev]
        s, u = montar_prompt(q, numeradas)
        ev = interpretar_eventos(llm.gerar(s, u, esquema=ESQUEMA_EVENTOS).texto, datas) or []
        juntas = {}
        for x in ev: juntas.setdefault(x.evidencia, []).append(x.descricao)
        r = {"n": n, "filtro": filtro, "contexto": ctx, "por_evidencia": por_ev, "todas_juntas": juntas}
        saida.append(r); print(json.dumps(r, ensure_ascii=False), flush=True)
json.dump(saida, open(sys.argv[0].replace(".py", ".json"), "w"), ensure_ascii=False, indent=1)
