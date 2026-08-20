"""add sequences for cpf rg email token numbering

Revision ID: 54d2d9b532ff
Revises: d3f422d9574d
Create Date: 2026-08-18 00:00:00.000000

Mesmo padrao de f4ab1864de74: cleaner.py (Task 2) passa a anonimizar CPF, RG
e e-mail pessoal alem de pessoa/processo — cada tipo novo precisa da sua
propria sequence pra numeracao de token atomica e independente.
"""
from typing import Sequence as TypingSequence, Union

from alembic import op
from sqlalchemy import Sequence
from sqlalchemy.schema import CreateSequence, DropSequence

# revision identifiers, used by Alembic.
revision: str = '54d2d9b532ff'
down_revision: Union[str, None] = 'd3f422d9574d'
branch_labels: Union[str, TypingSequence[str], None] = None
depends_on: Union[str, TypingSequence[str], None] = None

SEQUENCES = [
    'seq_entidades_anonimizadas_cpf',
    'seq_entidades_anonimizadas_rg',
    'seq_entidades_anonimizadas_email',
]


def upgrade() -> None:
    for nome in SEQUENCES:
        op.execute(CreateSequence(Sequence(nome)))


def downgrade() -> None:
    for nome in SEQUENCES:
        op.execute(DropSequence(Sequence(nome)))
