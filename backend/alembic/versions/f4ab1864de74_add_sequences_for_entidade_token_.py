"""add sequences for entidade token numbering

Revision ID: f4ab1864de74
Revises: 12bfda604a84
Create Date: 2026-08-09 00:00:00.000000

_obter_ou_criar_token numerava o token com COUNT(*)+1 sobre a tabela inteira:
alem de nao ser atomico (ver migration 12bfda604a84, que so faz a corrida
falhar alto), o custo cresce com o tamanho da tabela a cada entidade nova.
Uma sequence do Postgres por tipo resolve os dois problemas de uma vez —
nextval() e atomico (sem race entre execucoes concorrentes) e O(1)
independente do tamanho da tabela.
"""
from typing import Sequence as TypingSequence, Union

from alembic import op
from sqlalchemy import Sequence
from sqlalchemy.schema import CreateSequence, DropSequence

# revision identifiers, used by Alembic.
revision: str = 'f4ab1864de74'
down_revision: Union[str, None] = '12bfda604a84'
branch_labels: Union[str, TypingSequence[str], None] = None
depends_on: Union[str, TypingSequence[str], None] = None

SEQUENCES = ['seq_entidades_anonimizadas_pessoa', 'seq_entidades_anonimizadas_processo']


def upgrade() -> None:
    for nome in SEQUENCES:
        op.execute(CreateSequence(Sequence(nome)))


def downgrade() -> None:
    for nome in SEQUENCES:
        op.execute(DropSequence(Sequence(nome)))
