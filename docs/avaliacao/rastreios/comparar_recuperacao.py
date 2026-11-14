import importlib.util, sys
from collections import defaultdict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.avaliacao.ground_truth import carregar_ground_truth
from app.avaliacao.itens import mapa_item_logico
from app.avaliacao.metricas import agrupar_fragmentos, revocacao_em_k, rank_reciproco, ndcg_em_k
from app.core.config import REPO_ROOT, settings
from app.grafo.cliente import obter_driver
from app.ingestion.indexador import _obter_cliente_qdrant
import app.recuperacao.orquestrador as orq
from app.recuperacao import fusao
from app.recuperacao.lexico import buscar_lexico as bm25

spec = importlib.util.spec_from_file_location("lexico_ts_rank", sys.argv[1]); antigo = importlib.util.module_from_spec(spec); spec.loader.exec_module(antigo)
fundir_original = fusao.fundir_rrf

def fundir_com_profundidade(p):
    def f(l, v, g, k, rrf_k=fusao.RRF_K):
        return fundir_original(l[:p], v[:p], g[:p], k, rrf_k)
    return f

VARIANTES = {
    "ts_rank, RRF 50": (antigo.buscar_lexico, fundir_original),
    "BM25, RRF 50": (bm25, fundir_original),
    "BM25, RRF 20": (bm25, fundir_com_profundidade(20)),
    "BM25, RRF 10": (bm25, fundir_com_profundidade(10)),
}
CAMADAS = {"A": frozenset({"lexico", "vetorial", "grafo"}), "C": frozenset({"lexico"})}
perguntas = [p for p in carregar_ground_truth(REPO_ROOT / "docs/avaliacao/ground_truth.yaml") if p.itens_relevantes]
s = sessionmaker(bind=create_engine(settings.database_url))(); q = _obter_cliente_qdrant(); d = obter_driver()
mapa = mapa_item_logico(s)
print(f"{len(perguntas)} perguntas com itens relevantes")
for nome, (lex, fun) in VARIANTES.items():
    orq.buscar_lexico, orq.fundir_rrf = lex, fun
    for cfg in sys.argv[2].split(","):
        por_cat = defaultdict(list)
        for p in perguntas:
            ids = [e.item_id_canonico for e in orq.recuperar(p.pergunta, s, q, d, k=5, camadas=CAMADAS[cfg])]
            r = agrupar_fragmentos(ids, mapa); rel = set(p.itens_relevantes)
            m = (revocacao_em_k(r, rel), rank_reciproco(r, rel), ndcg_em_k(r, rel))
            por_cat[p.categoria].append(m); por_cat["TOTAL"].append(m)
        linha = "  ".join(f"{c[:10]}: R{sum(x[0] for x in v)/len(v):.2f}/M{sum(x[1] for x in v)/len(v):.2f}" for c, v in sorted(por_cat.items()))
        print(f"{nome:16} [{cfg}] {linha}")
