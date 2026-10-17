import csv

import pytest

from app.avaliacao.ground_truth import PerguntaReferencia
from app.avaliacao.relatorio import (
    custo,
    escrever_csv,
    linhas_diagnostico,
    linhas_revisao,
    montar_relatorio,
    tabela_ragas,
    tabela_recuperacao,
    taxas_abstencao,
)


def _p(id_, categoria, relevantes=(), sequencia=()):
    return PerguntaReferencia(
        id=id_,
        categoria=categoria,
        origem="autor",
        pergunta=f"{id_}?",
        resposta_referencia="ref",
        itens_relevantes=tuple(relevantes),
        trechos_evidencia=tuple("t" for _ in relevantes),
        sequencia_cronologica=tuple(sequencia),
        tipo_dificuldade="",
        observacao="",
    )


PERGUNTAS = [
    _p("q1", "intra_exata", ["i1"]),
    _p("q2", "longitudinal", ["i2", "i3"], ["i2", "i3"]),
    _p("q3", "sem_evidencia"),
]


def _rec(pid, config, logico):
    return {"pergunta_id": pid, "config": config, "ranking": logico, "ranking_logico": logico}


REC = [
    _rec("q1", "A", ["i1", "x"]),
    _rec("q2", "A", ["x", "i2"]),
    _rec("q3", "A", ["x"]),
    _rec("q1", "B", ["x"]),
    _rec("q2", "B", ["x"]),
    _rec("q3", "B", ["x"]),
]


def test_tabela_recuperacao_ignora_sem_evidencia_e_tem_media_geral():
    tabela = tabela_recuperacao(PERGUNTAS, REC)

    assert "sem_evidencia" not in tabela
    linha_a_geral = next(linha for linha in tabela.splitlines() if linha.startswith("| A | todas"))
    assert "| 2 | 0,200 | 0,750 | 0,750 |" in linha_a_geral


def _ger(pid, config, abstencao, fontes=(), tin=100, tout=10, erro=None):
    return {
        "pergunta_id": pid,
        "config": config,
        "texto": "t",
        "abstencao": abstencao,
        "fontes": list(fontes),
        "fontes_logicas": list(fontes),
        "contextos": ["c"],
        "tokens_entrada": tin,
        "tokens_saida": tout,
        "truncada": False,
        "erro": erro,
    }


GER = [
    _ger("q1", "A", False, ["i1"]),
    _ger("q2", "A", True),
    _ger("q3", "A", True),
    _ger("q1", "B", False, ["x"]),
    _ger("q2", "B", False, ["i2"]),
    _ger("q3", "B", False, ["x"]),
]


def test_taxas_abstencao():
    taxas = taxas_abstencao(PERGUNTAS, GER)

    assert taxas["A"] == {"correta": 1.0, "indevida": 0.5}
    assert taxas["B"] == {"correta": 0.0, "indevida": 0.0}


def test_tabela_ragas_media_ignora_none():
    rag = [
        {
            "pergunta_id": "q1",
            "config": "A",
            "faithfulness": 1.0,
            "answer_relevancy": None,
            "context_precision": 0.5,
            "context_recall": 0.5,
            "erros": {},
        },
        {
            "pergunta_id": "q2",
            "config": "A",
            "faithfulness": 0.5,
            "answer_relevancy": 0.8,
            "context_precision": None,
            "context_recall": 1.0,
            "erros": {},
        },
    ]

    tabela = tabela_ragas(PERGUNTAS, rag)

    linha = next(linha for linha in tabela.splitlines() if linha.startswith("| A | todas"))
    assert "0,750 (2)" in linha
    assert "0,800 (1)" in linha


def test_custo():
    rag = [{"tokens_juiz_entrada": 1_000_000, "tokens_juiz_saida": 100_000}]
    ger = [_ger("q1", "A", False, tin=1_000_000, tout=100_000)]

    valores = custo(ger, rag, "claude-sonnet-5-5", "claude-opus-5-5")

    assert valores["gerador_usd"] == pytest.approx(3.0)
    assert valores["juiz_usd"] == pytest.approx(6.0)
    assert valores["total_usd"] == pytest.approx(9.0)


DESCRICOES = {
    "i1": {
        "orgao": "CT",
        "data_reuniao": "2025-01-01",
        "numero_reuniao": 1,
        "assunto": "A",
        "texto": "texto i1",
        "pagina_inicio": 1,
    },
    "i2": {
        "orgao": "CCE",
        "data_reuniao": "2024-01-01",
        "numero_reuniao": 2,
        "assunto": "B",
        "texto": "texto i2",
        "pagina_inicio": 2,
    },
    "i3": {
        "orgao": "CCE",
        "data_reuniao": "2024-06-01",
        "numero_reuniao": 3,
        "assunto": "B",
        "texto": "texto i3",
        "pagina_inicio": 1,
    },
}


def test_linhas_revisao_uma_por_item_e_uma_para_sem_evidencia():
    linhas = linhas_revisao(PERGUNTAS, DESCRICOES)

    assert [(linha["pergunta_id"], linha["item_id"]) for linha in linhas] == [
        ("q1", "i1"),
        ("q2", "i2"),
        ("q2", "i3"),
        ("q3", ""),
    ]
    assert linhas[0]["texto_item"] == "texto i1"
    assert linhas[0]["orgao"] == "CT"


def test_linhas_diagnostico_config_a():
    linhas = linhas_diagnostico(PERGUNTAS, GER, REC, DESCRICOES)

    q1, q2, q3 = linhas
    assert q1["citou_relevante"] == "sim"
    assert q1["fontes_fora_do_gabarito"] == ""
    assert q1["atas_citadas"] == "CT 2025-01-01"
    assert q2["abstencao"] == "sim"
    assert q2["cobertura_sequencia"] == "0,50"
    assert q3["diagnostico"] == ""


def test_escrever_csv(tmp_path):
    caminho = tmp_path / "x.csv"
    escrever_csv(caminho, [{"a": "1", "b": "ação"}])

    with caminho.open(encoding="utf-8") as arquivo:
        assert list(csv.DictReader(arquivo)) == [{"a": "1", "b": "ação"}]


def test_montar_relatorio_tem_as_secoes():
    texto = montar_relatorio(PERGUNTAS, REC, GER, [], "claude-sonnet-5-5", "claude-opus-5-5")

    for titulo in ("## Recuperação", "## Geração (RAGAS)", "## Abstenção", "## Custo"):
        assert titulo in texto
