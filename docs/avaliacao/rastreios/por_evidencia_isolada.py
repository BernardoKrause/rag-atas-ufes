import json, sys, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.geracao.prompt as pr
from app.core.config import settings
from app.geracao.contexto import montar_contexto
from app.geracao.eventos import interpretar_eventos, ler_resposta_direta, montar_texto
from app.geracao.llm import criar_cliente_llm
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant
from app.recuperacao.orquestrador import recuperar
sys.path.insert(0, "../docs/avaliacao/rastreios")
from variantes_v3 import dcc  # noqa: E402

import difflib, re
from app.geracao.eventos import RE_MARCADOR


def direta_v2(bruta, eventos):
    try:
        frase = json.loads(bruta[bruta.find("{"):]).get("resposta", "")
    except Exception:
        return ""
    if not isinstance(frase, str) or not frase.strip() or re.search(r"[{}\n]", frase):
        return ""
    numeros = {int(n) for m in RE_MARCADOR.findall(frase) for n in re.findall(r"\d+", m)}
    citaveis = {e.evidencia for e in eventos}
    if not numeros:
        if len(eventos) != 1:
            return ""
        frase = frase.rstrip(". ") + f" [{eventos[0].evidencia}]."
    elif not numeros <= citaveis:
        return ""
    limpa = RE_MARCADOR.sub("", frase).strip(" .").lower()
    if any(difflib.SequenceMatcher(None, limpa, e.descricao.strip(" .").lower()).ratio() >= 0.8 for e in eventos):
        return ""
    return frase.strip()


s = sessionmaker(bind=create_engine(settings.database_url))(); q = _obter_cliente_qdrant(); d = obter_driver(); llm = criar_cliente_llm()
perguntas = json.load(open(sys.argv[1]))
VARIANTE = sys.argv[2] if len(sys.argv) > 2 else "ISO"
if VARIANTE == "ISO2":
    alvo = '"descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação registrado, ou vazio se não for relevante>"}]}'
    novo = '"descricao": "<o que ocorreu naquela reunião e o desfecho registrado (aprovação, rejeição, retirada de pauta, adiamento ou resultado da votação, que costuma vir no fim do trecho), ou vazio se não for relevante>"}]}'
    assert alvo in pr.SISTEMA, "variante não aplicada"
    pr.SISTEMA = pr.SISTEMA.replace(alvo, novo)
if VARIANTE == "ISOR":
    alvo = '"descricao": "<o que ocorreu naquela reunião, com a decisão ou o resultado da votação registrado, ou vazio se não for relevante>"}]}'
    novo = '"descricao": "<o que ocorreu naquela reunião em resposta ao que a pergunta pede, com a decisão ou o resultado da votação registrado e, se a pergunta pedir, o órgão ou outro dado das relações, ou vazio se não for relevante>"}]}'
    assert alvo in pr.SISTEMA, "variante não aplicada"
    pr.SISTEMA = pr.SISTEMA.replace(alvo, novo)
for rotulo, p in perguntas.items():
    numeradas = dcc() if rotulo == "DCC" else montar_contexto(recuperar(p, s, q, d), s)
    datas = {e.numero: e.data_reuniao for e in numeradas}
    inicio = time.time(); eventos, vereditos = [], []
    for e in numeradas:
        sis, usu = pr.montar_prompt(p, [e])
        bruta = llm.gerar(sis, usu, esquema=pr.ESQUEMA_EVENTOS)
        evs = interpretar_eventos(bruta.texto, datas) or []
        eventos += evs
        vereditos.append((e.numero, bool(evs), json.loads(bruta.texto[bruta.texto.find('{'):])["eventos"][0].get("descricao", "")[:80] if not evs else ""))
    eventos.sort(key=lambda ev: datas[ev.evidencia])
    t1 = time.time() - inicio
    direta_bruta = ""
    if eventos and VARIANTE in ("ISO", "ISO2"):
        sis, usu = pr.montar_prompt_resposta(p, eventos, numeradas)
        direta_bruta = llm.gerar(sis, usu, esquema=pr.ESQUEMA_RESPOSTA).texto
    citados = {ev.evidencia for ev in eventos}
    print(f"--- {VARIANTE} {rotulo} contexto={len(numeradas)} eventos={t1:.0f}s total={time.time()-inicio:.0f}s")
    direta = ler_resposta_direta(direta_bruta, citados) if VARIANTE == "ISO" else direta_v2(direta_bruta, eventos)
    print(montar_texto(eventos, datas, direta) if eventos else "ABSTENÇÃO")
    print("  descartadas:", [(n, desc) for n, ok, desc in vereditos if not ok])
    print("  direta bruta:", direta_bruta)
    sys.stdout.flush()
