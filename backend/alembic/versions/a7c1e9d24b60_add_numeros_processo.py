"""add numeros_processo

Revision ID: a7c1e9d24b60
Revises: c4d8e2f1a9b3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7c1e9d24b60'
down_revision: Union[str, None] = 'c4d8e2f1a9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'numeros_processo',
        sa.Column('token', sa.String(length=50), primary_key=True),
        sa.Column('numero', sa.String(length=40), nullable=False),
    )
    op.create_index('ix_numeros_processo_numero', 'numeros_processo', ['numero'])


def downgrade() -> None:
    op.drop_table('numeros_processo')
