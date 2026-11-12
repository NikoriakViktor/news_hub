"""category: expand — новий стовпець nullable і заповнення наявних рядків (data migration)

Стара версія застосунку про category не знає й далі вставляє рядки без неї — тому nullable.
NOT NULL — наступною міграцією (0003), коли нова версія застосунку вже всюди.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Таблиця «як у цій міграції», а не імпорт моделі: модель зміниться, а міграція має працювати завжди.
news = sa.table("news", sa.column("id", sa.Integer), sa.column("url", sa.String), sa.column("category", sa.String))


def upgrade() -> None:
    with op.batch_alter_table("news") as batch:
        batch.add_column(sa.Column("category", sa.String(length=100), nullable=True))
    op.execute(
        news.update()
        .where(news.c.category.is_(None))
        .values(category=sa.case((news.c.url.like("%/economy/%"), "Економіка"), else_="Новини"))
    )


def downgrade() -> None:
    with op.batch_alter_table("news") as batch:
        batch.drop_column("category")
