from app.services.order_status import (
    DEPLOYED_ORDER_STATUSES,
    is_successful_placement,
    normalize_broker_status,
)


def test_normalize_dhan_traded_to_filled():
    assert normalize_broker_status("TRADED") == "FILLED"
    assert normalize_broker_status("COMPLETE") == "FILLED"
    assert normalize_broker_status("traded") == "FILLED"


def test_normalize_working_and_rejected():
    assert normalize_broker_status("TRANSIT") == "PENDING"
    assert normalize_broker_status("PENDING") == "PENDING"
    assert normalize_broker_status(None) == "PENDING"
    assert normalize_broker_status("REJECTED") == "REJECTED"
    assert normalize_broker_status("CANCELLED") == "CANCELLED"
    assert normalize_broker_status("PAPER_FILLED") == "PAPER_FILLED"


def test_deployed_statuses_include_live_dhan_aliases():
    assert "TRADED" in DEPLOYED_ORDER_STATUSES
    assert "PENDING" in DEPLOYED_ORDER_STATUSES
    assert "FILLED" in DEPLOYED_ORDER_STATUSES
    assert "REJECTED" not in DEPLOYED_ORDER_STATUSES


def test_successful_placement_includes_traded():
    assert is_successful_placement("TRADED")
    assert is_successful_placement("PENDING")
    assert is_successful_placement("PAPER_FILLED")
    assert not is_successful_placement("REJECTED")
