from types import SimpleNamespace

import pytest

from order_time import apply_expiration
from time_utils import ServerOffsetUnavailable, set_derived_offset

ORDER_TIME_GTC = 0
ORDER_TIME_SPECIFIED = 2


@pytest.fixture(autouse=True)
def _known_offset(monkeypatch):
    """Default to a zero broker offset so passthrough assertions hold; tests that
    care about the offset override it explicitly."""
    monkeypatch.delenv("MT5_SERVER_UTC_OFFSET_SECONDS", raising=False)
    set_derived_offset(0)
    yield
    set_derived_offset(None)


def test_absent_expiration_leaves_gtc_untouched():
    req = {"action": 5, "type_time": ORDER_TIME_GTC, "type_filling": 1}
    apply_expiration(req, {})
    assert req["type_time"] == ORDER_TIME_GTC
    assert "expiration" not in req


def test_none_expiration_is_a_noop():
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": None})
    assert req["type_time"] == ORDER_TIME_GTC
    assert "expiration" not in req


def test_expiration_switches_to_specified():
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": 1780917192})
    assert req["type_time"] == ORDER_TIME_SPECIFIED
    assert req["expiration"] == 1780917192


def test_string_expiration_is_coerced_to_int():
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": "1780917192"})
    assert req["expiration"] == 1780917192
    assert isinstance(req["expiration"], int)


def test_expiration_is_shifted_into_server_time_by_the_offset():
    set_derived_offset(10800)
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": 1780917192})
    assert req["expiration"] == 1780917192 + 10800


def test_gtd_order_is_rejected_when_offset_is_unresolved():
    set_derived_offset(None)
    req = {"type_time": ORDER_TIME_GTC}
    with pytest.raises(ServerOffsetUnavailable):
        apply_expiration(req, {"expiration": 1780917192})


def test_returns_the_same_dict_for_chaining():
    req = {"type_time": ORDER_TIME_GTC}
    assert apply_expiration(req, {"expiration": 1780917192}) is req


def test_modify_preserves_existing_gtd_expiration():
    req = {"type_time": ORDER_TIME_GTC}
    existing = SimpleNamespace(
        type_time=ORDER_TIME_SPECIFIED, time_expiration=2_000_000_000
    )

    apply_expiration(req, {}, existing_order=existing)

    assert req["type_time"] == ORDER_TIME_SPECIFIED
    assert req["expiration"] == 2_000_000_000


def test_modify_can_override_existing_expiration():
    req = {"type_time": ORDER_TIME_GTC}
    existing = SimpleNamespace(
        type_time=ORDER_TIME_SPECIFIED, time_expiration=2_000_000_000
    )

    apply_expiration(req, {"expiration": 2_100_000_000}, existing_order=existing)

    assert req["expiration"] == 2_100_000_000
