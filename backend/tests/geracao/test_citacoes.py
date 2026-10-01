from app.geracao.citacoes import processar_citacoes

VALIDOS = {1, 2, 3, 4, 5}


def test_extrai_marcadores_validos():
    texto, citados = processar_citacoes("A proposta foi aprovada [1] e publicada [3].", VALIDOS)
    assert citados == {1, 3}
    assert texto == "A proposta foi aprovada [1] e publicada [3]."


def test_remove_marcador_inexistente():
    texto, citados = processar_citacoes("Foi aprovada [9].", VALIDOS)
    assert citados == set()
    assert texto == "Foi aprovada."


def test_mantem_validos_e_remove_invalidos_no_mesmo_texto():
    texto, citados = processar_citacoes("Aprovada [2] e revogada [7].", VALIDOS)
    assert citados == {2}
    assert texto == "Aprovada [2] e revogada."


def test_marcadores_repetidos_contam_uma_vez():
    _, citados = processar_citacoes("Primeiro [1]. Depois [1].", VALIDOS)
    assert citados == {1}


def test_marcadores_colados_sao_separados_por_espaco():
    texto, citados = processar_citacoes("Aprovada[1][2].", VALIDOS)
    assert citados == {1, 2}
    assert texto == "Aprovada [1] [2]."


def test_marcador_com_espacos_internos_e_normalizado():
    texto, citados = processar_citacoes("Aprovada [ 2 ].", VALIDOS)
    assert citados == {2}
    assert texto == "Aprovada [2]."


def test_marcador_com_lista_de_numeros_vira_marcadores_individuais():
    texto, citados = processar_citacoes("Aprovada [1, 2, 8].", VALIDOS)
    assert citados == {1, 2}
    assert texto == "Aprovada [1][2]."


def test_texto_sem_marcadores_devolve_conjunto_vazio():
    texto, citados = processar_citacoes("Não há citações aqui.", VALIDOS)
    assert citados == set()
    assert texto == "Não há citações aqui."


def test_colchete_sem_numero_nao_e_marcador():
    texto, citados = processar_citacoes("Trecho omitido [...] no original [1].", VALIDOS)
    assert citados == {1}
    assert texto == "Trecho omitido [...] no original [1]."
