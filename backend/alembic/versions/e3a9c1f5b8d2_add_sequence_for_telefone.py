"""add sequence for telefone token numbering

Revision ID: e3a9c1f5b8d2
Revises: b7e2c4a9d1f3
Create Date: 2026-10-06 00:00:00.000000

Mesmo padrao de b7e2c4a9d1f3: celular pessoal vira tipo de entidade
anonimizada, com a sua sequence de numeracao de token.
"""
from typing import Sequence as TypingSequence, Union

from alembic import op
from sqlalchemy import Sequence
from sqlalchemy.schema import CreateSequence, DropSequence

# revision identifiers, used by Alembic.
revision: str = 'e3a9c1f5b8d2'
down_revision: Union[str, None] = 'b7e2c4a9d1f3'
branch_labels: Union[str, TypingSequence[str], None] = None
depends_on: Union[str, TypingSequence[str], None] = None


def upgrade() -> None:
    op.execute(CreateSequence(Sequence('seq_entidades_anonimizadas_telefone')))


def downgrade() -> None:
    op.execute(DropSequence(Sequence('seq_entidades_anonimizadas_telefone')))
