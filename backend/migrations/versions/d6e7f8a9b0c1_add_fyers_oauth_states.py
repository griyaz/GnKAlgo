"""Persist one-time FYERS OAuth state values."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fyers_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_fyers_oauth_states_user_id", "fyers_oauth_states", ["user_id"])
    op.create_index("ix_fyers_oauth_states_state_hash", "fyers_oauth_states", ["state_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_fyers_oauth_states_state_hash", table_name="fyers_oauth_states")
    op.drop_index("ix_fyers_oauth_states_user_id", table_name="fyers_oauth_states")
    op.drop_table("fyers_oauth_states")
