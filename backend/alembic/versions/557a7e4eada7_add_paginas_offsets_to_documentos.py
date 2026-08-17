"""add paginas_offsets to documentos

Revision ID: 557a7e4eada7
Revises: 232ff4002927
Create Date: 2026-08-12 22:15:57.729406

Necessario pro segmentador (Parte 3) mapear cada item de pauta pra pagina do
PDF onde ele aparece. Nulo nos documentos ja ingeridos ate serem reprocessados
por um rerun idempotente do pipeline.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '557a7e4eada7'
down_revision: Union[str, None] = '232ff4002927'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documentos', sa.Column('paginas_offsets', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('documentos', 'paginas_offsets')
