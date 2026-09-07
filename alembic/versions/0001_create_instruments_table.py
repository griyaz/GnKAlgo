"""Alembic migration: create instruments table

Drop this file into your alembic/versions directory and run `alembic upgrade head`.
If your project uses a different alembic env, adapt the import path for `now()` default.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_create_instruments_table'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("segment", sa.String(length=32), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("trading_symbol", sa.String(length=128), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("instrument_type", sa.String(length=64), nullable=True),
        sa.Column("index_name", sa.String(length=128), nullable=True),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("broker", sa.String(length=64), nullable=True),
        sa.Column("broker_symbol", sa.String(length=128), nullable=True),
        sa.Column("broker_token", sa.String(length=128), nullable=True),
        sa.Column("tick_size", sa.Numeric(18, 8), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint("exchange", "symbol", name="uq_instruments_exchange_symbol"),
    )
    op.create_index("ix_instruments_broker_token", "instruments", ["broker_token"])


def downgrade():
    op.drop_index("ix_instruments_broker_token", table_name="instruments")
    op.drop_table("instruments")
