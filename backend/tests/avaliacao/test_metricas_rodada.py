import pytest

from app.avaliacao.metricas_rodada import (
    agregar,
    avaliar_ranking,
    linhas_do_ranking,
    origem_por_item,
    ranking_logico,
    relevantes_da_referencia,
)


def test_exemplo_do_orientador_um_relevante_na_quinta_posicao():
    avaliacao = avaliar_ranking(["x1", "x2", "x3", "x4", "r1"], {"r1", "r2", "r3"}, 5)

    assert (avaliacao["tp"], avaliacao["fp"], avaliacao["fn"]) == (1, 4, 2)
    assert avaliacao["precisao"] == pytest.approx(0.2)
    assert avaliacao["revocacao"] == pytest.approx(1 / 3)
    assert avaliacao["rr"] == pytest.approx(0.2)
    assert avaliacao["dcg"] == pytest.approx(0.38685, abs=1e-5)
    assert avaliacao["idcg"] == pytest.approx(2.13093, abs=1e-5)
    assert avaliacao["ndcg"] == pytest.approx(0.18154, abs=1e-5)
    assert avaliacao["faltantes"] == ["r2", "r3"]


def test_revocacao_maxima_com_doze_relevantes():
    relevantes = {f"r{i}" for i in range(12)}

    avaliacao = avaliar_ranking([f"r{i}" for i in range(5)], relevantes, 5)

    assert avaliacao["revocacao"] == pytest.approx(5 / 12)
    assert avaliacao["revocacao_maxima"] == pytest.approx(5 / 12)
    assert avaliacao["ndcg"] == pytest.approx(1.0)


def test_lista_curta_mantem_denominador_k_e_sem_relevante_da_rr_zero():
    avaliacao = avaliar_ranking(["x1", "x2"], {"r1"}, 5)

    assert avaliacao["itens_na_lista"] == 2
    assert avaliacao["precisao"] == 0
    assert avaliacao["rr"] == 0.0
    assert avaliacao["primeira_posicao_relevante"] is None


def test_sem_relevantes_nao_divide_por_zero():
    avaliacao = avaliar_ranking(["x1"], set(), 5)

    assert avaliacao["revocacao"] is None
    assert avaliacao["ndcg"] is None


def test_media_por_pergunta_e_micro_do_exemplo_ficticio():
    um = avaliar_ranking(["a"], {"a"}, 5)
    nove = avaliar_ranking(["b1"], {f"b{i}" for i in range(1, 10)}, 5)

    resumo = agregar([um, nove])

    assert resumo["revocacao_media"] == pytest.approx((1 + 1 / 9) / 2)
    assert resumo["revocacao_micro"] == pytest.approx(0.2)


def test_agregar_ignora_perguntas_sem_relevantes():
    resumo = agregar([avaliar_ranking(["a"], {"a"}, 5), avaliar_ranking(["x"], set(), 5)])

    assert resumo["perguntas"] == 1


def test_fragmentos_do_mesmo_item_contam_uma_vez():
    mapa = {"i1_F1": "i1"}

    ranking = ranking_logico(["i1", "i1_F1", "i2"], mapa)
    avaliacao = avaliar_ranking(ranking, {"i1"}, 5)

    assert ranking == ["i1", "i2"]
    assert avaliacao["tp"] == 1


def test_relevantes_da_referencia_usa_item_logico_e_separa_evidencia_sem_identificador():
    referencia = {"evidencias": [
        {"identificador_item": "i1_F1"}, {"identificador_item": "i1"}, {"identificador_item": None, "ata": "x.pdf"},
    ]}

    relevantes, sem_id = relevantes_da_referencia(referencia, {"i1_F1": "i1"})

    assert relevantes == {"i1"}
    assert sem_id == [{"identificador_item": None, "ata": "x.pdf"}]


def test_linhas_do_ranking_mostram_origem_de_cada_item():
    fusao = [
        {"item_id_canonico": "i1", "pontuacao": 0.03, "posicoes": {"lexico": 1}},
        {"item_id_canonico": "i1_F1", "pontuacao": 0.02, "posicoes": {"vetorial": 2}},
        {"item_id_canonico": "i2", "pontuacao": 0.01, "posicoes": {"grafo": 1}},
    ]
    mapa = {"i1_F1": "i1"}

    linhas = linhas_do_ranking(["i1", "i2"], {"i2"}, origem_por_item(fusao, mapa))

    assert linhas[0]["fragmentos"] == ["i1", "i1_F1"]
    assert linhas[0]["posicoes_nas_buscas"] == {"lexico": 1, "vetorial": 2}
    assert linhas[1] == {
        "posicao": 2, "item_id": "i2", "relevante": True, "fragmentos": ["i2"],
        "posicoes_nas_buscas": {"grafo": 1}, "pontuacao_rrf": 0.01,
    }
