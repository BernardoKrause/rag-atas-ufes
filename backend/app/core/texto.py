from __future__ import annotations

import re
import unicodedata


def remover_acentos_maiusculo(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").upper()


def slugificar(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", remover_acentos_maiusculo(texto)).strip("_")
