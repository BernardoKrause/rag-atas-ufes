import json
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.avaliacao.itens import mapa_item_logico
from app.core.config import settings
from app.geracao.llm import criar_cliente_llm
from app.geracao.prompt import montar_prompt
from app.geracao.respondedor import responder_detalhado
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant
from app.models.documento import Documento
from app.models.item_pauta import ItemPauta
from app.recuperacao.fusao import ancorar, fundir_rrf
from app.recuperacao.grafo import expandir_grafo
from app.recuperacao.lexico import buscar_lexico
from app.recuperacao.orquestrador import _so_do_orgao
from app.recuperacao.setor import documentos_do_orgao, identificar_orgao
from app.recuperacao.orquestrador import K_PADRAO, TOP_N_ANCORA_PADRAO, recuperar
from app.recuperacao.vetorial import buscar_vetorial


def descrever(sessao, ids):
    linhas = sessao.execute(
        select(ItemPauta, Documento)
        .join(Documento, ItemPauta.documento_id == Documento.id_documento)
        .where(ItemPauta.item_id_canonico.in_(ids))
    ).all()
    return {
        i.item_id_canonico: {
            "ata": d.id_documento,
            "orgao": d.orgao,
            "data": d.data_reuniao.isoformat(),
            "pagina": i.pagina_inicio,
            "assunto": (i.assunto or "")[:90],
        }
        for i, d in linhas
    }


def camada(hits, desc, limite):
    return [
        {"rank": h.rank, "item": h.item_id_canonico, "score": h.score, **desc.get(h.item_id_canonico, {})}
        for h in hits[:limite]
    ]


def main():
    pergunta, saida = sys.argv[1], Path(sys.argv[2])
    termos = sys.argv[3:]
    sessao = sessionmaker(bind=create_engine(settings.database_url))()
    qdrant, driver = _obter_cliente_qdrant(), obter_driver()

    orgao = identificar_orgao(pergunta, sessao)
    documentos = documentos_do_orgao(orgao, sessao) if orgao else None
    lex = buscar_lexico(pergunta, sessao, orgao=orgao)
    vet = buscar_vetorial(pergunta, qdrant, documentos=documentos)
    anc = ancorar(lex, vet, top_n=TOP_N_ANCORA_PADRAO)
    gra = expandir_grafo(anc, driver)
    if orgao:
        gra = _so_do_orgao(gra, orgao, sessao)
    fus = fundir_rrf(lex, vet, gra, k=K_PADRAO)
    fus20 = fundir_rrf(lex, vet, gra, k=20)
    evid = recuperar(pergunta, sessao, qdrant, driver)
    assert [e.item_id_canonico for e in evid] == fus, "fusão reproduzida diverge do orquestrador"

    alvos = [
        i.item_id_canonico
        for i in sessao.execute(select(ItemPauta)).scalars()
        if all(t.lower() in i.texto.lower() for t in termos)
    ] if termos else []
    todos = {h.item_id_canonico for h in [*lex, *vet, *gra]} | set(fus20) | set(alvos)
    desc = descrever(sessao, todos)

    def posicao(item, hits):
        return next((h.rank for h in hits if h.item_id_canonico == item), None)

    detalhada = responder_detalhado(pergunta, sessao, qdrant, driver, criar_cliente_llm())
    numeradas = detalhada.evidencias
    logico = mapa_item_logico(sessao)
    unicos = list(dict.fromkeys(logico[i] for i in fus))
    assert [logico[e.fonte.item_id_canonico] for e in numeradas] == unicos, "contexto diverge da fusão"
    usuarios = [montar_prompt(pergunta, [e])[1] for e in numeradas]
    saidas = detalhada.saidas_eventos
    texto = detalhada.resposta.texto
    citados = {f.numero for f in detalhada.resposta.fontes}

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    rastreio = {
        "id_execucao": uuid.uuid4().hex[:12],
        "quando": datetime.now().isoformat(timespec="seconds"),
        "commit": commit,
        "config": {"k": K_PADRAO, "top_n_ancora": TOP_N_ANCORA_PADRAO, "camadas": "lexico+vetorial+grafo",
                   "modelo": settings.llm_modelo, "num_ctx": settings.llm_num_ctx, "temperatura": 0},
        "pergunta": pergunta,
        "alvos": {a: {**desc[a], "rank_lexico": posicao(a, lex), "rank_vetorial": posicao(a, vet),
                      "rank_grafo": posicao(a, gra), "posicao_fusao_top20": fus20.index(a) + 1 if a in fus20 else None}
                  for a in alvos},
        "lexico_top10": camada(lex, desc, 10),
        "vetorial_top10": camada(vet, desc, 10),
        "ancoras": [h.item_id_canonico for h in anc],
        "grafo_top10": camada(gra, desc, 10),
        "fusao_top20": [{"posicao": n, "item": i, **desc[i]} for n, i in enumerate(fus20, 1)],
        "contexto_enviado": [{"numero": e.numero, "item": e.fonte.item_id_canonico, "rotulo": e.fonte.rotulo,
                              "pagina": e.fonte.pagina, "texto": e.texto, "frases_grafo": e.frases_grafo, "data_reuniao": str(e.data_reuniao)}
                             for e in numeradas],
        "prompts_usuario": usuarios,
        "tokens_entrada": sum(s.tokens_entrada or 0 for s in saidas),
        "tokens_saida": sum(s.tokens_saida or 0 for s in saidas),
        "truncada": any(s.truncada for s in saidas),
        "respostas_brutas": [s.texto for s in saidas],
        "resposta_direta_bruta": detalhada.saida_resposta.texto if detalhada.saida_resposta else None,
        "resposta_final": texto,
        "citados": sorted(citados),
    }
    saida.write_text(json.dumps(rastreio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: rastreio[k] for k in ("id_execucao", "alvos", "tokens_entrada", "truncada", "citados")},
                     ensure_ascii=False, indent=1))
    for e in rastreio["contexto_enviado"]:
        print(e["numero"], e["item"], e["rotulo"])
    print("BRUTAS:", rastreio["respostas_brutas"])
    print("FINAL:", texto)


if __name__ == "__main__":
    main()
