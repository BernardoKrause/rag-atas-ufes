"""add orgao and composite unique to documentos

Revision ID: 232ff4002927
Revises: f4ab1864de74
Create Date: 2026-08-10 19:42:07.436518

nome_arquivo sozinho nao identifica uma ata de forma confiavel: orgaos
diferentes podem nomear atas com o mesmo padrao generico (ex.: "10-2025.pdf"),
o que fazia processar_ata encontrar o registro do outro orgao pelo select por
nome_arquivo e sobrescrever seus dados em silencio. Adiciona a coluna 'orgao'
(codigo bruto do inventario) e troca a unique constraint pra composta
(tipo_orgao, orgao, nome_arquivo), que e o que de fato identifica uma ata.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '232ff4002927'
down_revision: Union[str, None] = 'f4ab1864de74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documentos', sa.Column('orgao', sa.String(length=50), nullable=False))
    op.drop_constraint('uq_documentos_nome_arquivo', 'documentos', type_='unique')
    op.create_unique_constraint(
        'uq_documentos_tipo_orgao_orgao_nome_arquivo',
        'documentos',
        ['tipo_orgao', 'orgao', 'nome_arquivo'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_documentos_tipo_orgao_orgao_nome_arquivo', 'documentos', type_='unique'
    )
    op.create_unique_constraint(
        'uq_documentos_nome_arquivo', 'documentos', ['nome_arquivo']
    )
    op.drop_column('documentos', 'orgao')
