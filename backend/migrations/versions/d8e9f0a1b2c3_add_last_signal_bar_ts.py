"""Remember last SMC candle so scheduled runs do not restack orders.

Revision ID: d8e9f0a1b2c3
Revises: c4d5e6f7a8b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("last_signal_bar_ts", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("strategies", "last_signal_bar_ts")
