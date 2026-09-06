"""widen broker_connections.broker for fyers/upstox

Revision ID: a1b2c3d4e5f6
Revises: 91a5c3ef7b20

BrokerType gained FYERS/UPSTOX. The column is a non-native enum (plain VARCHAR,
no CHECK constraint), so only the length needs to grow to hold "upstox" (6).
Widen to 20 to future-proof. SQLite is dynamically typed, so batch mode makes
this a no-op there; on PostgreSQL it issues an ALTER COLUMN TYPE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "91a5c3ef7b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("broker_connections") as batch_op:
        batch_op.alter_column(
            "broker",
            existing_type=sa.String(length=5),
            type_=sa.String(length=20),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("broker_connections") as batch_op:
        batch_op.alter_column(
            "broker",
            existing_type=sa.String(length=20),
            type_=sa.String(length=5),
            existing_nullable=False,
        )
