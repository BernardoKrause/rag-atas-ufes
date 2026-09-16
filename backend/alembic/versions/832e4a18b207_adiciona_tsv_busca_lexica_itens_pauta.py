"""adiciona tsv busca lexica itens_pauta

Revision ID: 832e4a18b207
Revises: d949572db9fe
Create Date: 2026-09-11 20:16:33.789652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '832e4a18b207'
down_revision: Union[str, None] = 'd949572db9fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'itens_pauta',
        sa.Column(
            'tsv',
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('portuguese', texto)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index('ix_itens_pauta_tsv', 'itens_pauta', ['tsv'], postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('ix_itens_pauta_tsv', table_name='itens_pauta')
    op.drop_column('itens_pauta', 'tsv')
