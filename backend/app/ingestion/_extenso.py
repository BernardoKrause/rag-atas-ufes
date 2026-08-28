"""Parsing de numerais cardinais por extenso em português (usado para horários)."""

import re

NUM_UNIDADE = {
    "UM": 1, "UMA": 1, "DOIS": 2, "DUAS": 2,
    "TRÊS": 3, "TRES": 3,
    "QUATRO": 4, "CINCO": 5, "SEIS": 6, "SETE": 7, "OITO": 8, "NOVE": 9,
}
NUM_10_19 = {
    "DEZ": 10, "ONZE": 11, "DOZE": 12, "TREZE": 13, "QUATORZE": 14, "CATORZE": 14,
    "QUINZE": 15, "DEZESSEIS": 16, "DEZESSETE": 17, "DEZOITO": 18, "DEZENOVE": 19,
}
NUM_DEZENA = {
    "VINTE": 20, "TRINTA": 30, "QUARENTA": 40, "CINQUENTA": 50,
    "SESSENTA": 60, "SETENTA": 70, "OITENTA": 80, "NOVENTA": 90,
}
ZERO = {"ZERO": 0}

_RE_TOKEN = re.compile("[A-Z" + chr(0xC0) + "-" + chr(0xDE) + chr(0xFFFD) + "]+|\\d+")


def tokenizar(texto: str) -> list[str]:
    return _RE_TOKEN.findall(texto.upper())


def parse_cardinal(tokens: list[str], i: int) -> tuple[int | None, int]:
    """Tenta parsear um numero cardinal (extenso ou digito) a partir do indice i.
    Retorna (valor, proximo_indice) ou (None, i) se nao conseguir."""
    if i >= len(tokens):
        return None, i
    tok = tokens[i]
    if tok.isdigit():
        return int(tok), i + 1
    if tok in NUM_DEZENA:
        valor = NUM_DEZENA[tok]
        j = i + 1
        if j < len(tokens) and tokens[j] == "E" and j + 1 < len(tokens) and tokens[j + 1] in NUM_UNIDADE:
            return valor + NUM_UNIDADE[tokens[j + 1]], j + 2
        return valor, j
    if tok in NUM_10_19:
        return NUM_10_19[tok], i + 1
    if tok in NUM_UNIDADE:
        return NUM_UNIDADE[tok], i + 1
    if tok in ZERO:
        return 0, i + 1
    return None, i
