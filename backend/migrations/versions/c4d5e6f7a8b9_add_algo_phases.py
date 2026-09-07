"""Add signal expansion, strategy versions, backtests and paper trading."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in (
        ("exchange", sa.Column("exchange", sa.String(12), nullable=False, server_default="NSE")),
        ("entry_min", sa.Column("entry_min", sa.Float())),
        ("entry_max", sa.Column("entry_max", sa.Float())),
        ("stop_loss", sa.Column("stop_loss", sa.Float())),
        ("target_1", sa.Column("target_1", sa.Float())),
        ("target_2", sa.Column("target_2", sa.Float())),
        ("timeframe", sa.Column("timeframe", sa.String(12), nullable=False, server_default="15m")),
        ("status", sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE")),
        ("explanation", sa.Column("explanation", sa.Text())),
        ("strategy_source", sa.Column("strategy_source", sa.String(120))),
        ("model_source", sa.Column("model_source", sa.String(120))),
        ("execution_mode", sa.Column("execution_mode", sa.String(12), nullable=False, server_default="PAPER")),
        ("routed_order_id", sa.Column("routed_order_id", sa.Uuid(), nullable=True)),
    ):
        op.add_column("signals", column)

    op.add_column("strategies", sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("strategies", sa.Column("paper_verified_at", sa.DateTime(timezone=True)))
    op.add_column("strategy_runs", sa.Column("strategy_version_id", sa.Uuid(), nullable=True))

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("changelog", sa.Text()),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])
    with op.batch_alter_table("strategy_runs") as batch_op:
        batch_op.create_foreign_key(
            "fk_strategy_runs_strategy_version", "strategy_versions", ["strategy_version_id"], ["id"]
        )
    with op.batch_alter_table("signals") as batch_op:
        batch_op.create_foreign_key("fk_signals_routed_order", "orders", ["routed_order_id"], ["id"])

    for table, columns in (
        ("backtest_runs", [
            sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("strategy_id", sa.Uuid()), sa.Column("strategy_version_id", sa.Uuid()),
            sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"),
            sa.Column("input_hash", sa.String(64), nullable=False), sa.Column("candles_count", sa.Integer(), nullable=False),
            sa.Column("initial_capital", sa.Float(), nullable=False), sa.Column("final_equity", sa.Float(), nullable=False),
            sa.Column("total_return", sa.Float(), nullable=False), sa.Column("max_drawdown", sa.Float(), nullable=False),
            sa.Column("trade_count", sa.Integer(), nullable=False), sa.Column("metrics_json", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("backtest_trades", [
            sa.Column("id", sa.Uuid(), nullable=False), sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("side", sa.String(8), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False), sa.Column("entry_price", sa.Float(), nullable=False),
            sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False), sa.Column("exit_price", sa.Float(), nullable=False),
            sa.Column("pnl", sa.Float(), nullable=False), sa.Column("reason", sa.String(32), nullable=False),
        ]),
        ("paper_trading_runs", [
            sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("strategy_id", sa.Uuid()), sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
            sa.Column("initial_cash", sa.Float(), nullable=False), sa.Column("cash", sa.Float(), nullable=False),
            sa.Column("realized_pnl", sa.Float(), nullable=False), sa.Column("unrealized_pnl", sa.Float(), nullable=False),
            sa.Column("max_daily_loss", sa.Float(), nullable=False), sa.Column("max_position_qty", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
        ]),
        ("paper_fills", [
            sa.Column("id", sa.Uuid(), nullable=False), sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("order_id", sa.Uuid()), sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("side", sa.String(8), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False), sa.Column("fee", sa.Float(), nullable=False),
            sa.Column("filled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("paper_positions", [
            sa.Column("id", sa.Uuid(), nullable=False), sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("average_price", sa.Float(), nullable=False), sa.Column("last_price", sa.Float()),
            sa.Column("realized_pnl", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
    ):
        constraints = [sa.PrimaryKeyConstraint("id")]
        if table == "backtest_runs":
            constraints += [sa.ForeignKeyConstraint(["user_id"], ["users.id"]), sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]), sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.id"])]
        elif table == "backtest_trades":
            constraints += [sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"])]
        elif table == "paper_trading_runs":
            constraints += [sa.ForeignKeyConstraint(["user_id"], ["users.id"]), sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"])]
        elif table == "paper_fills":
            constraints += [sa.ForeignKeyConstraint(["run_id"], ["paper_trading_runs.id"]), sa.ForeignKeyConstraint(["order_id"], ["orders.id"])]
        else:
            constraints += [sa.ForeignKeyConstraint(["run_id"], ["paper_trading_runs.id"])]
        op.create_table(table, *columns, *constraints)
        if table != "backtest_trades":
            op.create_index(f"ix_{table}_user_id" if table in {"backtest_runs", "paper_trading_runs"} else f"ix_{table}_run_id", table, ["user_id" if table in {"backtest_runs", "paper_trading_runs"} else "run_id"])
    with op.batch_alter_table("paper_positions") as batch_op:
        batch_op.create_unique_constraint("uq_paper_position", ["run_id", "symbol"])


def downgrade() -> None:
    with op.batch_alter_table("signals") as batch_op:
        batch_op.drop_constraint("fk_signals_routed_order", type_="foreignkey")
    with op.batch_alter_table("strategy_runs") as batch_op:
        batch_op.drop_constraint("fk_strategy_runs_strategy_version", type_="foreignkey")
    with op.batch_alter_table("paper_positions") as batch_op:
        batch_op.drop_constraint("uq_paper_position", type_="unique")
    for table in ("paper_positions", "paper_fills", "paper_trading_runs", "backtest_trades", "backtest_runs"):
        op.drop_table(table)
    op.drop_index("ix_strategy_versions_strategy_id", table_name="strategy_versions")
    op.drop_table("strategy_versions")
    op.drop_column("strategy_runs", "strategy_version_id")
    op.drop_column("strategies", "paper_verified_at")
    op.drop_column("strategies", "current_version")
    for name in ("routed_order_id", "execution_mode", "model_source", "strategy_source", "explanation", "status", "timeframe", "target_2", "target_1", "stop_loss", "entry_max", "entry_min", "exchange"):
        op.drop_column("signals", name)
