import pytest

from app.avaliacao.metricas import (
    agrupar_fragmentos,
    cobertura_sequencia,
    ndcg_em_k,
    precisao_em_k,
    rank_reciproco,
    revocacao_em_k,
)

RANKING = ["a", "b", "c", "d", "e"]
RELEVANTES = {"b", "e", "x"}


def test_agrupar_fragmentos_mantem_a_posicao_do_primeiro():
    mapa = {"a": "a", "a_F1": "a", "b": "b"}

    assert agrupar_fragmentos(["a_F1", "b", "a"], mapa) == ["a", "b"]


def test_agrupar_fragmentos_id_fora_do_mapa_fica_como_esta():
    assert agrupar_fragmentos(["z"], {}) == ["z"]


def test_precisao():
    assert precisao_em_k(RANKING, RELEVANTES) == pytest.approx(0.4)


def test_precisao_usa_denominador_k_mesmo_com_ranking_curto():
    assert precisao_em_k(["b"], RELEVANTES) == pytest.approx(0.2)


def test_revocacao():
    assert revocacao_em_k(RANKING, RELEVANTES) == pytest.approx(2 / 3)


def test_revocacao_ignora_relevante_fora_do_top_k():
    assert revocacao_em_k(["a", "c", "d", "f", "g", "b"], {"b"}) == 0.0


def test_rank_reciproco():
    assert rank_reciproco(RANKING, RELEVANTES) == pytest.approx(0.5)


def test_rank_reciproco_sem_relevante_e_zero():
    assert rank_reciproco(RANKING, {"x"}) == 0.0


def test_ndcg():
    assert ndcg_em_k(RANKING, RELEVANTES) == pytest.approx(0.4776237, abs=1e-6)


def test_ndcg_ideal_e_um():
    assert ndcg_em_k(["b", "e", "x"], RELEVANTES) == pytest.approx(1.0)


def test_relevantes_vazios_levantam_erro():
    with pytest.raises(ValueError):
        revocacao_em_k(RANKING, set())
    with pytest.raises(ValueError):
        ndcg_em_k(RANKING, set())


def test_cobertura_sequencia():
    assert cobertura_sequencia({"s1", "s3", "z"}, ("s1", "s2", "s3", "s4")) == pytest.approx(0.5)
