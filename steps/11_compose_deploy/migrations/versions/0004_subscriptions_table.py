"""subscriptions — підписки чатів Telegram на ключові слова (урок 47)

Згенеровано `alembic revision --autogenerate` на SQLite; виправлено вручну, як у 0001 і 0003:
server_default=sa.func.now() (синтаксис SQLite) → sa.func.now().
chat_id — BigInteger: id чатів Telegram не вміщаються в 32 біти.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28 07:41:36.002901

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('keyword', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chat_id', 'keyword', name='uq_subscription_chat_keyword')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_chat_id'), ['chat_id'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_chat_id'))

    op.drop_table('subscriptions')
