"""category: contract — NOT NULL, коли всі версії застосунку вже пишуть category

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

news = sa.table("news", sa.column("category", sa.String))


def upgrade() -> None:
    # рядки, які стара версія встигла вставити між 0002 і 0003
    op.execute(news.update().where(news.c.category.is_(None)).values(category="Новини"))
    with op.batch_alter_table("news") as batch:
        batch.alter_column("category", existing_type=sa.String(length=100), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("news") as batch:
        batch.alter_column("category", existing_type=sa.String(length=100), nullable=True)
