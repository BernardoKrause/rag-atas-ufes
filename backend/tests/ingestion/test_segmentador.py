from app.ingestion.segmentador import _normalizar_com_mapa


def test_normalizar_com_mapa_colapsa_espacos_multiplos():
    normalizado, mapa = _normalizar_com_mapa("A   B")
    assert normalizado == "A B"
    assert len(mapa) == len(normalizado)


def test_normalizar_com_mapa_colapsa_quebras_de_linha():
    normalizado, mapa = _normalizar_com_mapa("A\n\n  B\nC")
    assert normalizado == "A B C"


def test_normalizar_com_mapa_preserva_offset_correto():
    original = "AB  CD"
    normalizado, mapa = _normalizar_com_mapa(original)
    assert normalizado == "AB CD"
    # o "C" normalizado (indice 3) deve apontar pro "C" original (indice 4)
    indice_c = normalizado.index("C")
    assert original[mapa[indice_c]] == "C"


def test_normalizar_com_mapa_string_vazia():
    normalizado, mapa = _normalizar_com_mapa("")
    assert normalizado == ""
    assert mapa == []
