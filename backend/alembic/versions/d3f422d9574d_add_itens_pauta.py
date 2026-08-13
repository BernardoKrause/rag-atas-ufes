"""add itens_pauta

Revision ID: d3f422d9574d
Revises: 557a7e4eada7
Create Date: 2026-08-12 22:20:18.755725

Nova tabela do segmentador estrutural (Parte 3): cada linha e um item de pauta
extraido de uma ata, com item_id_canonico como chave de correlacao logica
entre Postgres/Qdrant/Neo4j nas Partes 4/5. A unique composta
(documento_id, secao, numero_item, fragmento_indice) cobre o caso de um item
dividido em multiplos fragmentos por overflow de tamanho.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f422d9574d'
down_revision: Union[str, None] = '557a7e4eada7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'itens_pauta',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('documento_id', sa.Integer(), nullable=False),
        sa.Column('item_id_canonico', sa.String(length=120), nullable=False),
        sa.Column('secao', sa.String(length=30), nullable=False),
        sa.Column('numero_item', sa.String(length=20), nullable=False),
        sa.Column('fragmento_indice', sa.Integer(), nullable=False),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('pagina_inicio', sa.Integer(), nullable=True),
        sa.Column('pagina_fim', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['documento_id'], ['documentos.id_documento']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id_canonico', name='uq_itens_pauta_item_id_canonico'),
        sa.UniqueConstraint(
            'documento_id', 'secao', 'numero_item', 'fragmento_indice',
            name='uq_itens_pauta_documento_secao_numero_fragmento',
        ),
    )


def downgrade() -> None:
    op.drop_table('itens_pauta')
