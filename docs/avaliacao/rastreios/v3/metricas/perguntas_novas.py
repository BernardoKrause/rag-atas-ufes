import json
import sys
from pathlib import Path

from app.avaliacao.etapas import CONFIGURACOES, _registro_geracao
from app.avaliacao.executar import MODELO_GERADOR, _clientes
from app.avaliacao.itens import mapa_item_logico
from app.avaliacao.metricas import agrupar_fragmentos, ndcg_em_k, precisao_em_k, rank_reciproco, revocacao_em_k
from app.geracao.llm import criar_cliente_llm
from app.geracao.respondedor import responder_detalhado
from app.recuperacao.orquestrador import recuperar

PASTA = Path(sys.argv[1])
K = 5

PERGUNTAS = [
    {"id": "R4", "categoria": "intra_reformulada", "origem": "4",
     "pergunta": "Quais docentes foram escolhidos para ajudar a organizar a sétima edição da semana acadêmica capixaba do curso de alimentos no setor CCAE / DEAL?"},
    {"id": "R14", "categoria": "intra_reformulada", "origem": "14",
     "pergunta": "O que foi decidido sobre o balanço final da ação extensionista voltada à segurança alimentar em abrigos e casas de acolhimento de Alegre no setor CCENS / DFN?"},
    {"id": "R28", "categoria": "intra_reformulada", "origem": "28",
     "pergunta": "Como foi tratado o pedido de uma docente para se afastar por noventa dias, a partir de abril de 2023, para estudos de qualificação no país no setor CEFD?"},
    {"id": "R31", "categoria": "intra_reformulada", "origem": "31",
     "pergunta": "Qual foi o resultado da análise do balanço final do encontro regional de computação do norte do Espírito Santo realizado em novembro de 2024 no setor CEUNES / DCE?"},
    {"id": "R32", "categoria": "intra_reformulada", "origem": "32",
     "pergunta": "O departamento confirmou a aprovação que a chefia deu sozinha à inscrição de um projeto no edital da Prograd de 2022 no setor CEUNES / DCE?"},
    {"id": "S1", "categoria": "sem_evidencia", "origem": None,
     "pergunta": "Qual foi a decisão sobre a compra de um liofilizador para os laboratórios do curso no setor CCAE / DEAL?"},
    {"id": "S2", "categoria": "sem_evidencia", "origem": None,
     "pergunta": "Qual foi a decisão sobre a participação dos estudantes na Maratona de Programação no setor CCENS / DC?"},
    {"id": "S3", "categoria": "sem_evidencia", "origem": None,
     "pergunta": "Qual foi a decisão sobre o convênio de intercâmbio de estudantes com universidades da Finlândia no setor CE / COLEGIADO / PEDAGOGIA?"},
    {"id": "S4", "categoria": "sem_evidencia", "origem": None,
     "pergunta": "Qual foi a decisão sobre a instalação de painéis de energia solar nos prédios do campus no setor CEUNES?"},
    {"id": "S5", "categoria": "sem_evidencia", "origem": None,
     "pergunta": "Qual foi a decisão sobre a compra de óculos de realidade virtual para o laboratório no setor CEUNES / DCE?"},
]


def main():
    gabarito = {g["n"]: g for g in map(json.loads, (PASTA / "gabarito_itens.jsonl").open(encoding="utf-8"))}
    (PASTA / "perguntas_novas.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in PERGUNTAS) + "\n", encoding="utf-8"
    )
    Sessao, qdrant, driver = _clientes()
    cliente_llm = criar_cliente_llm()
    recuperacao, geracao = [], []
    try:
        with Sessao() as sessao:
            mapa = mapa_item_logico(sessao)
            for p in PERGUNTAS:
                relevantes = set()
                if p["origem"]:
                    relevantes = {mapa.get(i, i) for r in gabarito[p["origem"]]["registros"] for i in r["itens"]}
                for config, camadas in CONFIGURACOES.items():
                    evidencias = recuperar(p["pergunta"], sessao, qdrant, driver, k=K, camadas=camadas)
                    logico = agrupar_fragmentos([e.item_id_canonico for e in evidencias], mapa)
                    registro = {"id": p["id"], "categoria": p["categoria"], "config": config,
                                "relevantes": sorted(relevantes), "ranking_logico": logico}
                    if relevantes:
                        registro.update({
                            "acertos": [i for i in logico[:K] if i in relevantes],
                            "p5": precisao_em_k(logico, relevantes, K), "r5": revocacao_em_k(logico, relevantes, K),
                            "mrr": rank_reciproco(logico, relevantes, K), "ndcg5": ndcg_em_k(logico, relevantes, K),
                        })
                    recuperacao.append(registro)
                detalhada = responder_detalhado(p["pergunta"], sessao, qdrant, driver, cliente_llm,
                                                camadas=CONFIGURACOES["A"])
                g = _registro_geracao(p["id"], "A", MODELO_GERADOR, detalhada, mapa)
                g.update({"id": p["id"], "categoria": p["categoria"], "pergunta": p["pergunta"]})
                geracao.append(g)
                print(p["id"], "abstencao" if g["abstencao"] else "respondeu", flush=True)
    finally:
        driver.close()
        qdrant.close()
    for nome, linhas in (("recuperacao_novas.jsonl", recuperacao), ("geracao_novas.jsonl", geracao)):
        (PASTA / nome).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in linhas) + "\n",
                                  encoding="utf-8")


if __name__ == "__main__":
    main()
