"""add unique(tipo, token) to entidades_anonimizadas

Revision ID: 12bfda604a84
Revises: ed18c909a8f5
Create Date: 2026-08-09 00:00:00.000000

_obter_ou_criar_token numera tokens com um COUNT(*)+1 sobre a tabela; sem essa
constraint, duas execucoes concorrentes do pipeline (ex.: rodar o script duas
vezes ao mesmo tempo apontando pro mesmo banco) podem calcular o mesmo numero
e inserir duas entidades diferentes com o mesmo (tipo, token), corrompendo o
mapeamento de anonimizacao em silencio. A constraint nao evita a corrida, mas
faz o segundo INSERT falhar alto (IntegrityError) em vez de gravar dado
errado sem avisar.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '12bfda604a84'
down_revision: Union[str, None] = 'ed18c909a8f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_entidades_anonimizadas_tipo_token', 'entidades_anonimizadas', ['tipo', 'token']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_entidades_anonimizadas_tipo_token', 'entidades_anonimizadas', type_='unique'
    )
