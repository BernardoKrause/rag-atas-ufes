from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.recuperacao.tipos import LIMITE_PADRAO, Hit

# Robertson & Zaragoza (2009), valores usuais do Okapi BM25.
K1 = 1.2
B = 0.75

CONSULTA_BM25 = text(
    """
    WITH termos AS (
        SELECT DISTINCT unnest(tsvector_to_array(to_tsvector('portuguese', :pergunta))) AS termo
    ),
    tamanhos AS (
        SELECT i.item_id_canonico, i.tsv,
               (SELECT coalesce(sum(coalesce(array_length(u.positions, 1), 1)), 0)
                FROM unnest(i.tsv) u) AS tamanho
        FROM itens_pauta i
    ),
    colecao AS (
        SELECT count(*) AS n, greatest(avg(tamanho), 1) AS media FROM tamanhos
    ),
    ocorrencias AS (
        SELECT t.item_id_canonico, t.tamanho, u.lexeme,
               coalesce(array_length(u.positions, 1), 1) AS tf
        FROM tamanhos t, unnest(t.tsv) u
        WHERE u.lexeme IN (SELECT termo FROM termos)
    ),
    frequencia AS (
        SELECT lexeme, count(*) AS df FROM ocorrencias GROUP BY lexeme
    )
    SELECT o.item_id_canonico,
           sum(ln(1 + (c.n - f.df + 0.5) / (f.df + 0.5))
               * o.tf * (:k1 + 1)
               / (o.tf + :k1 * (1 - :b + :b * o.tamanho / c.media))) AS score
    FROM ocorrencias o
    JOIN frequencia f USING (lexeme)
    CROSS JOIN colecao c
    GROUP BY o.item_id_canonico
    ORDER BY score DESC, o.item_id_canonico
    LIMIT :limite
    """
)


def buscar_lexico(pergunta: str, sessao: Session, limite: int = LIMITE_PADRAO) -> list[Hit]:
    if not pergunta.strip():
        return []

    linhas = sessao.execute(
        CONSULTA_BM25, {"pergunta": pergunta, "k1": K1, "b": B, "limite": limite}
    ).all()
    return [
        Hit(item_id_canonico=linha.item_id_canonico, rank=indice + 1, score=float(linha.score))
        for indice, linha in enumerate(linhas)
    ]
