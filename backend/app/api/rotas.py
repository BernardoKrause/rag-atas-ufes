from __future__ import annotations

from fastapi import APIRouter

roteador = APIRouter()


@roteador.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
