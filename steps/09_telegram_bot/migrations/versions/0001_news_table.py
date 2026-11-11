"""news table — таблиця новин агрегатора (урок 38)

Згенеровано `alembic revision --autogenerate`; виправлено вручну: server_default=sa.text('now()')
(працює лише в PostgreSQL) → sa.func.now() (кожна база отримує свій SQL).

Revision ID: 0001
Revises: 
Create Date: 2026-09-27 11:09:07.290129

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('news',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('lang', sa.String(length=2), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('published_time', sa.Time(), nullable=True),
    sa.Column('scraped_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )
    op.create_index(op.f('ix_news_category'), 'news', ['category'], unique=False)
    op.create_index(op.f('ix_news_lang'), 'news', ['lang'], unique=False)
    op.create_index(op.f('ix_news_source'), 'news', ['source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_news_source'), table_name='news')
    op.drop_index(op.f('ix_news_lang'), table_name='news')
    op.drop_index(op.f('ix_news_category'), table_name='news')
    op.drop_table('news')
