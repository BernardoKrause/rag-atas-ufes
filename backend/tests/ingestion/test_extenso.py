from app.ingestion._extenso import parse_cardinal, tokenizar


def test_parse_cardinal_aceita_setenta_e_nove():
    tokens = tokenizar("SETENTA E NOVE")
    valor, proximo = parse_cardinal(tokens, 0)
    assert valor == 79
    assert proximo == len(tokens)


def test_parse_cardinal_aceita_dezena_pura_quarenta_a_noventa():
    for dezena, esperado in [("QUARENTA", 40), ("CINQUENTA", 50), ("SESSENTA", 60),
                              ("SETENTA", 70), ("OITENTA", 80), ("NOVENTA", 90)]:
        valor, _ = parse_cardinal(tokenizar(dezena), 0)
        assert valor == esperado, dezena
