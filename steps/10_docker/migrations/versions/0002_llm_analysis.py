"""llm analysis — колонки аналізу LLM у таблиці news (урок 43)

Згенеровано `alembic revision --autogenerate` і перечитано: усі колонки nullable — наявні рядки
лишаються без аналізу (NULL), дані не переписуються. batch_alter_table — бо env.py вмикає
render_as_batch для SQLite (там немає ALTER COLUMN); у PostgreSQL це звичайні ALTER TABLE.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27 17:10:09.622695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('news', schema=None) as batch_op:
        batch_op.add_column(sa.Column('summary', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('ai_category', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('sentiment', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('keywords', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_news_ai_category'), ['ai_category'], unique=False)
        batch_op.create_index(batch_op.f('ix_news_sentiment'), ['sentiment'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('news', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_news_sentiment'))
        batch_op.drop_index(batch_op.f('ix_news_ai_category'))
        batch_op.drop_column('analyzed_at')
        batch_op.drop_column('keywords')
        batch_op.drop_column('sentiment')
        batch_op.drop_column('ai_category')
        batch_op.drop_column('summary')
