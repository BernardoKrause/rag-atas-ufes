"""make tipo_reuniao nullable

Revision ID: f3c9b5e6a1d2
Revises: 5a0938342802
Create Date: 2026-07-25 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c9b5e6a1d2'
down_revision: Union[str, None] = '5a0938342802'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('documentos', 'tipo_reuniao',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)


def downgrade() -> None:
    op.alter_column('documentos', 'tipo_reuniao',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)
