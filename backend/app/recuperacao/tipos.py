from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    item_id_canonico: str
    rank: int
    score: float | None = None


@dataclass(frozen=True)
class Evidencia:
    item_id_canonico: str
    texto: str
    contexto_grafo: dict
    rank_final: int
    scores: dict[str, float | None]
