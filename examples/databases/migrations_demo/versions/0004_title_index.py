"""індекс за title без блокування запису (PostgreSQL: CREATE INDEX CONCURRENTLY)

CONCURRENTLY не можна виконати в транзакції, а Alembic загортає міграцію в транзакцію —
тому autocommit_block(). На SQLite postgresql_concurrently ігнорується: звичайний CREATE INDEX.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index("ix_news_title", "news", ["title"], postgresql_concurrently=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_news_title", table_name="news", postgresql_concurrently=True)
