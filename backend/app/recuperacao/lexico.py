from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.recuperacao.tipos import Hit

LIMITE_PADRAO = 50


def buscar_lexico(pergunta: str, sessao: Session, limite: int = LIMITE_PADRAO) -> list[Hit]:
    pergunta_or = " | ".join(pergunta.split())
    linhas = sessao.execute(
        text(
            """
            SELECT item_id_canonico, ts_rank(tsv, to_tsquery('portuguese', :pergunta)) AS score
            FROM itens_pauta
            WHERE tsv @@ to_tsquery('portuguese', :pergunta)
            ORDER BY score DESC
            LIMIT :limite
            """
        ),
        {"pergunta": pergunta_or, "limite": limite},
    ).all()
    return [
        Hit(item_id_canonico=linha.item_id_canonico, rank=indice + 1, score=float(linha.score))
        for indice, linha in enumerate(linhas)
    ]
