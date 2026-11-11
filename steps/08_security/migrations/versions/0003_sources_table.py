"""sources — RSS-джерела, які додає адмін (урок 46)

Згенеровано `alembic revision --autogenerate` на SQLite; виправлено вручну, як у 0001:
server_default=sa.func.now() (синтаксис SQLite) → sa.func.now() (кожна база — свій SQL).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28 05:34:25.139944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sources')
