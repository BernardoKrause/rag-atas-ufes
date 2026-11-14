import json, sys, time
exec(open(sys.argv[3]).read().split("s = sessionmaker(")[0])
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
s = sessionmaker(bind=create_engine(settings.database_url))(); q = _obter_cliente_qdrant(); d = obter_driver(); llm = criar_cliente_llm()
SIS2 = """Você responde perguntas sobre atas de reuniões de órgãos colegiados da UFES \
usando exclusivamente as evidências fornecidas. Escreva uma única frase que responda \
diretamente ao que a pergunta pede, usando o trecho e as relações das evidências. \
Não invente. Se as evidências não trouxerem o que a pergunta pede, devolva vazio."""
ESQ2 = {"type": "object", "properties": {"resposta": {"type": "string"}}, "required": ["resposta"]}
sis1, esq1 = variante("V1")
for rotulo, p in json.load(open(sys.argv[1])).items():
    numeradas = dcc() if rotulo == "DCC" else montar_contexto(recuperar(p, s, q, d), s)
    _, usuario = pr.montar_prompt(p, numeradas)
    t = time.time(); b1 = llm.gerar(sis1, usuario, esquema=esq1); t1 = time.time() - t
    datas = {e.numero: e.data_reuniao for e in numeradas}
    ev = interpretar_eventos(b1.texto, datas)
    citadas = [e for e in numeradas if ev and e.numero in {x.evidencia for x in ev}]
    t = time.time()
    r2 = json.loads(llm.gerar(SIS2, pr.montar_prompt(p, citadas)[1], esquema=ESQ2).texto)["resposta"] if citadas else ""
    t2 = time.time() - t
    print(f"--- {rotulo} (eventos {t1:.1f}s + resposta {t2:.1f}s)")
    print("RESPOSTA:", r2)
    print(montar_texto(ev, datas) if ev else "ABSTENÇÃO")
