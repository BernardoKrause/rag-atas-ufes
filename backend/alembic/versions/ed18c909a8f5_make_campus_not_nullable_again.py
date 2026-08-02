"""make campus not nullable again

Revision ID: ed18c909a8f5
Revises: f3c9b5e6a1d2
Create Date: 2026-08-02 00:00:00.000000

campus e derivavel a partir do centro (cada centro do corpus fica em
exatamente um campus fisico da UFES — ver CENTRO_CAMPUS em
app/ingestion/extractor.py), entao nunca precisa ficar nulo. A migration
5a0938342802 relaxou essa coluna pra contornar um extractor que tentava
(re)descobrir o campus fazendo regex no texto da ata, que so cita o nome do
campus em alguns modelos de ata — o extractor foi corrigido pra derivar o
campus do centro (sempre conhecido), entao a constraint volta ao normal.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed18c909a8f5'
down_revision: Union[str, None] = 'f3c9b5e6a1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CENTRO_CAMPUS = {
    "CAR": "Goiabeiras",
    "CCHN": "Goiabeiras",
    "CE": "Goiabeiras",
    "CEFD": "Goiabeiras",
    "CT": "Goiabeiras",
    "CCAE": "Alegre",
    "CCENS": "São Mateus",
    "CEUNES": "São Mateus",
}


def upgrade() -> None:
    documentos = sa.table(
        "documentos",
        sa.column("centro", sa.String),
        sa.column("campus", sa.String),
    )
    for centro, campus in CENTRO_CAMPUS.items():
        op.execute(
            documentos.update()
            .where(documentos.c.centro == centro, documentos.c.campus.is_(None))
            .values(campus=campus)
        )

    op.alter_column('documentos', 'campus',
               existing_type=sa.VARCHAR(length=30),
               nullable=False)


def downgrade() -> None:
    op.alter_column('documentos', 'campus',
               existing_type=sa.VARCHAR(length=30),
               nullable=True)
