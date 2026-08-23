"""add campos de enriquecimento a itens_pauta

Revision ID: d949572db9fe
Revises: ebd011f42ebe
Create Date: 2026-08-23 16:45:09.227189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd949572db9fe'
down_revision: Union[str, None] = 'ebd011f42ebe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('itens_pauta', sa.Column('assunto', sa.Text(), nullable=True))
    op.add_column('itens_pauta', sa.Column('tipo_desfecho', sa.String(30), nullable=True))
    op.add_column('itens_pauta', sa.Column('resultado_votacao', sa.Text(), nullable=True))
    op.add_column('itens_pauta', sa.Column('encaminhamento', sa.Text(), nullable=True))
    op.add_column('itens_pauta', sa.Column('ato_emitido', sa.String(60), nullable=True))
    op.add_column('itens_pauta', sa.Column('departamento_origem', sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column('itens_pauta', 'departamento_origem')
    op.drop_column('itens_pauta', 'ato_emitido')
    op.drop_column('itens_pauta', 'encaminhamento')
    op.drop_column('itens_pauta', 'resultado_votacao')
    op.drop_column('itens_pauta', 'tipo_desfecho')
    op.drop_column('itens_pauta', 'assunto')
