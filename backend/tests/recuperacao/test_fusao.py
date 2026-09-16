from app.recuperacao.fusao import ancorar, fundir_rrf
from app.recuperacao.tipos import Hit


def test_ancorar_uniao_top_n_de_ambas_as_listas():
    hits_lexico = [Hit("a", 1), Hit("b", 2), Hit("c", 3)]
    hits_vetorial = [Hit("c", 1), Hit("d", 2)]

    ancoras = ancorar(hits_lexico, hits_vetorial, top_n=2)

    ids = {hit.item_id_canonico for hit in ancoras}
    assert ids == {"a", "b", "c", "d"}


def test_ancorar_mantem_menor_rank_quando_item_aparece_nas_duas_listas():
    hits_lexico = [Hit("a", 5)]
    hits_vetorial = [Hit("a", 1)]

    ancoras = ancorar(hits_lexico, hits_vetorial, top_n=10)

    assert ancoras == [Hit("a", 1)]


def test_ancorar_respeita_top_n():
    hits_lexico = [Hit("a", 1), Hit("b", 2), Hit("c", 3)]

    ancoras = ancorar(hits_lexico, [], top_n=1)

    assert [hit.item_id_canonico for hit in ancoras] == ["a"]


def test_fundir_rrf_prioriza_item_presente_em_mais_listas():
    hits_lexico = [Hit("a", 1), Hit("b", 2)]
    hits_vetorial = [Hit("b", 1), Hit("a", 2)]
    hits_grafo = [Hit("b", 1)]

    resultado = fundir_rrf(hits_lexico, hits_vetorial, hits_grafo, k=2)

    assert resultado == ["b", "a"]


def test_fundir_rrf_respeita_k():
    hits_lexico = [Hit("a", 1), Hit("b", 2), Hit("c", 3)]

    resultado = fundir_rrf(hits_lexico, [], [], k=2)

    assert resultado == ["a", "b"]


def test_fundir_rrf_com_grafo_vazio_ainda_funciona():
    hits_lexico = [Hit("a", 1)]
    hits_vetorial = [Hit("a", 1)]

    resultado = fundir_rrf(hits_lexico, hits_vetorial, [], k=5)

    assert resultado == ["a"]
