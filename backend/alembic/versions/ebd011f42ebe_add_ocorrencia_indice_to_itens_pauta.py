"""add ocorrencia_indice to itens_pauta

Revision ID: ebd011f42ebe
Revises: 54d2d9b532ff
Create Date: 2026-08-18 12:47:16.948548

segmentador.py (Task 5) passa a desambiguar itens que compartilham
(documento_id, secao, numero_item) via um indice de ocorrencia crescente, em
vez de deixar a constraint unica estourar (achado (c) da bateria e2e:
numeracao duplicada na fonte + falso positivo de citacao narrativa).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebd011f42ebe'
down_revision: Union[str, None] = '54d2d9b532ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'itens_pauta',
        sa.Column('ocorrencia_indice', sa.Integer(), nullable=False, server_default='0'),
    )
    op.drop_constraint(
        'uq_itens_pauta_documento_secao_numero_fragmento', 'itens_pauta', type_='unique'
    )
    op.create_unique_constraint(
        'uq_itens_pauta_documento_secao_numero_ocorrencia_fragmento',
        'itens_pauta',
        ['documento_id', 'secao', 'numero_item', 'ocorrencia_indice', 'fragmento_indice'],
    )


def downgrade() -> None:
    # o schema antigo (sem ocorrencia_indice) nao consegue representar itens
    # que so se diferenciam por ocorrencia_indice > 0 (numeracao duplicada
    # desambiguada pelo segmentador — ver Task 5) — nao ha como "mesclar"
    # essas linhas sem perder dado, entao o downgrade e destrutivo por
    # necessidade: descarta as ocorrencias extras antes de recriar a
    # constraint antiga
    op.execute("DELETE FROM itens_pauta WHERE ocorrencia_indice > 0")

    op.drop_constraint(
        'uq_itens_pauta_documento_secao_numero_ocorrencia_fragmento', 'itens_pauta', type_='unique'
    )
    op.create_unique_constraint(
        'uq_itens_pauta_documento_secao_numero_fragmento',
        'itens_pauta',
        ['documento_id', 'secao', 'numero_item', 'fragmento_indice'],
    )
    op.drop_column('itens_pauta', 'ocorrencia_indice')
