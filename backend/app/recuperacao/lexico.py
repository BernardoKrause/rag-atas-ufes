from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.recuperacao.tipos import Hit

LIMITE_PADRAO = 50


def buscar_lexico(pergunta: str, sessao: Session, limite: int = LIMITE_PADRAO) -> list[Hit]:
    termos = pergunta.split()
    if not termos:
        return []

    consulta_or = " || ".join(f"plainto_tsquery('portuguese', :termo{i})" for i in range(len(termos)))
    parametros = {f"termo{i}": termo for i, termo in enumerate(termos)}
    parametros["limite"] = limite

    linhas = sessao.execute(
        text(
            f"""
            SELECT item_id_canonico, ts_rank(tsv, {consulta_or}) AS score
            FROM itens_pauta
            WHERE tsv @@ ({consulta_or})
            ORDER BY score DESC
            LIMIT :limite
            """
        ),
        parametros,
    ).all()
    return [
        Hit(item_id_canonico=linha.item_id_canonico, rank=indice + 1, score=float(linha.score))
        for indice, linha in enumerate(linhas)
    ]
