"""Canonicalize broker order statuses used by risk checks and run records."""

# Live DhanHQ place-order responses use TRADED / TRANSIT / PENDING, not FILLED.
# Strategies never reconcile fills later, so these must count as deployed capital.
FILLED_STATUSES = frozenset({"FILLED", "PAPER_FILLED", "TRADED", "COMPLETE", "COMPLETED"})
WORKING_STATUSES = frozenset(
    {"PENDING", "TRANSIT", "OPEN", "TRIGGER PENDING", "PARTIALLY FILLED", "PART TRADED"}
)
REJECTED_STATUSES = frozenset({"REJECTED", "REJECT"})
CANCELLED_STATUSES = frozenset({"CANCELLED", "CANCELED", "EXPIRED"})

# SQL filter for max_daily_loss: filled, working, and raw Dhan aliases.
DEPLOYED_ORDER_STATUSES = tuple(FILLED_STATUSES | WORKING_STATUSES)


def normalize_broker_status(raw: str | None) -> str:
    status = (raw or "PENDING").strip().upper()
    if status == "PAPER_FILLED":
        return "PAPER_FILLED"
    if status in FILLED_STATUSES:
        return "FILLED"
    if status in REJECTED_STATUSES:
        return "REJECTED"
    if status in CANCELLED_STATUSES:
        return "CANCELLED"
    return "PENDING"


def is_successful_placement(status: str | None) -> bool:
    """True when a strategy run should be treated as having placed an order."""
    normalized = normalize_broker_status(status)
    return normalized in {"FILLED", "PAPER_FILLED", "PENDING"}
