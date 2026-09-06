from app.ingestion.indexador import gerar_janelas


def test_gerar_janelas_texto_menor_que_janela_gera_uma_unica_janela():
    token_ids = list(range(50))

    janelas = gerar_janelas(token_ids)

    assert len(janelas) == 1
    assert janelas[0].indice == 0
    assert janelas[0].offset_inicio == 0
    assert janelas[0].offset_fim == 50
    assert janelas[0].token_ids == token_ids


def test_gerar_janelas_aplica_sobreposicao_entre_janelas_consecutivas():
    token_ids = list(range(250))

    janelas = gerar_janelas(token_ids)

    assert [j.indice for j in janelas] == [0, 1, 2]
    assert (janelas[0].offset_inicio, janelas[0].offset_fim) == (0, 120)
    assert (janelas[1].offset_inicio, janelas[1].offset_fim) == (100, 220)
    assert (janelas[2].offset_inicio, janelas[2].offset_fim) == (200, 250)
    assert janelas[1].token_ids == token_ids[100:220]


def test_gerar_janelas_lista_vazia_nao_gera_janelas():
    assert gerar_janelas([]) == []
