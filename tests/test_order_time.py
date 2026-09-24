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


def _reader(ticks_ms):
    """A read_tick_ms callable returning each value in turn, then the last; counts reads."""
    calls = {"n": 0}

    def read():
        value = ticks_ms[min(calls["n"], len(ticks_ms) - 1)]
        calls["n"] += 1
        return value

    return read, calls


def test_a_cached_offset_is_used_without_reading_the_quote(monkeypatch):
    set_derived_offset(10800)
    now = 1_785_000_000
    monkeypatch.setattr("time_utils.time.time", lambda: now)
    read, calls = _reader([(now - 9000) * 1000])
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(
        req, {"expiration": now + 600}, symbol="XAUUSDm", read_tick_ms=read
    )
    assert req["expiration"] == now + 600 + 10800
    assert calls["n"] == 0


def test_without_an_offset_a_moving_quote_on_the_orders_symbol_derives_it(monkeypatch):
    # No usable offset yet (e.g. the broker has no EURUSD and the refresher has not run):
    # the order's own symbol quotes, and once its tick moves it derives the offset.
    monkeypatch.setenv("MT5_TIME_ORDER_DERIVE_DELAY", "0")
    set_derived_offset(None)
    now = 1_785_000_000
    monkeypatch.setattr("time_utils.time.time", lambda: now)
    server_ms = (now + 3 * 3600 + 2) * 1000
    read, calls = _reader([server_ms, server_ms, server_ms + 180])
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(
        req, {"expiration": now + 600}, symbol="BTCUSDm", read_tick_ms=read
    )
    assert req["type_time"] == ORDER_TIME_SPECIFIED
    assert req["expiration"] == now + 600 + 3 * 3600
    assert calls["n"] == 3


def test_without_an_offset_a_frozen_quote_refuses_the_gtd_order(monkeypatch):
    # A frozen quote may be stale by whole hours; it must not derive, so the order is
    # refused rather than placed at a guessed time.
    monkeypatch.setenv("MT5_TIME_ORDER_DERIVE_ATTEMPTS", "4")
    monkeypatch.setenv("MT5_TIME_ORDER_DERIVE_DELAY", "0")
    set_derived_offset(None)
    now = 1_785_000_000
    monkeypatch.setattr("time_utils.time.time", lambda: now)
    read, calls = _reader([(now - 3600 + 20) * 1000])
    req = {"type_time": ORDER_TIME_GTC}
    with pytest.raises(ServerOffsetUnavailable):
        apply_expiration(
            req, {"expiration": now + 600}, symbol="BTCUSDm", read_tick_ms=read
        )
    assert calls["n"] == 4
