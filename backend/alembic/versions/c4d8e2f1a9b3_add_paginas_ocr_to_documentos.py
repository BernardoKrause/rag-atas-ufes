"""add paginas_ocr to documentos

Revision ID: c4d8e2f1a9b3
Revises: e3a9c1f5b8d2
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d8e2f1a9b3'
down_revision: Union[str, None] = 'e3a9c1f5b8d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documentos',
        sa.Column('paginas_ocr', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column('documentos', 'paginas_ocr')
