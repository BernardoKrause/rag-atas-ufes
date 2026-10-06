"""add sequences for siape matricula link_pessoal token numbering

Revision ID: b7e2c4a9d1f3
Revises: 832e4a18b207
Create Date: 2026-10-06 00:00:00.000000

Mesmo padrao de 54d2d9b532ff: SIAPE, matricula e links que identificam
pessoa (Lattes, sala pessoal do conferenciaweb) viram tipos de entidade
anonimizada, cada um com a sua sequence de numeracao de token.
"""
from typing import Sequence as TypingSequence, Union

from alembic import op
from sqlalchemy import Sequence
from sqlalchemy.schema import CreateSequence, DropSequence

# revision identifiers, used by Alembic.
revision: str = 'b7e2c4a9d1f3'
down_revision: Union[str, None] = '832e4a18b207'
branch_labels: Union[str, TypingSequence[str], None] = None
depends_on: Union[str, TypingSequence[str], None] = None

SEQUENCES = [
    'seq_entidades_anonimizadas_siape',
    'seq_entidades_anonimizadas_matricula',
    'seq_entidades_anonimizadas_link_pessoal',
]


def upgrade() -> None:
    for nome in SEQUENCES:
        op.execute(CreateSequence(Sequence(nome)))


def downgrade() -> None:
    for nome in SEQUENCES:
        op.execute(DropSequence(Sequence(nome)))
