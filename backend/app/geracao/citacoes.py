from __future__ import annotations

import re

RE_MARCADOR = re.compile(r"[ \t]*\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")


def processar_citacoes(texto: str, numeros_validos: set[int]) -> tuple[str, set[int]]:
    citados: set[int] = set()

    def substituir(marcador: re.Match) -> str:
        numeros = [int(n) for n in re.split(r"\s*,\s*", marcador.group(1))]
        validos = [n for n in numeros if n in numeros_validos]
        citados.update(validos)
        if not validos:
            return ""
        return " " + "".join(f"[{n}]" for n in validos)

    return RE_MARCADOR.sub(substituir, texto).strip(), citados
