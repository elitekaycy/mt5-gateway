import threading
import time
from types import SimpleNamespace

import mt5_connection
from mt5_connection import SerializedMT5
from time_utils import resolve_offset_seconds, set_derived_offset


def test_serialized_mt5_prevents_concurrent_native_calls():
    state = SimpleNamespace(active=0, maximum=0)
    state_lock = threading.Lock()

    class StubMT5:
        @staticmethod
        def account_info():
            with state_lock:
                state.active += 1
                state.maximum = max(state.maximum, state.active)
            time.sleep(0.01)
            with state_lock:
                state.active -= 1
            return object()

    mt5 = SerializedMT5(StubMT5())
    threads = [threading.Thread(target=mt5.account_info) for _ in range(12)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert state.maximum == 1


def test_call_atomic_prevents_interleaving_between_call_sequences():
    events = []
    first_call_started = threading.Event()

    class StubMT5:
        @staticmethod
        def record(value):
            events.append(value)
            if value == "first-start":
                first_call_started.set()
                time.sleep(0.02)

    mt5 = SerializedMT5(StubMT5())

    first = threading.Thread(
        target=lambda: mt5.call_atomic(
            lambda native: (
                native.record("first-start"),
                native.record("first-end"),
            )
        )
    )
    second = threading.Thread(
        target=lambda: (first_call_started.wait(), mt5.record("second"))
    )

    first.start()
    second.start()
    first.join()
    second.join()

    assert events == ["first-start", "first-end", "second"]


def test_wrapper_forwards_positional_only_calls_without_kwargs_splat():
    """MetaTrader5's request functions (order_check, order_send) return None
    with (-2, 'Unnamed arguments not allowed') when invoked with a kwargs
    splat, even an empty one. The wrapper must therefore call `function(*args)`
    when no kwargs were given. A pure-Python stub cannot observe the splat
    itself (only the C extension distinguishes the call shapes), so this test
    pins the observable contract: both call styles reach the native function
    with the right arguments. The C-level behavior was verified against a live
    terminal under Wine: retcode 0 with the fix, -2 without it.
    """
    calls = []

    class StubMT5:
        @staticmethod
        def order_check(request):
            calls.append(("args", request))
            return object()

        @staticmethod
        def copy_rates_from(symbol, timeframe=None):
            calls.append(("kwargs", symbol, timeframe))
            return object()

    mt5 = SerializedMT5(StubMT5())
    assert mt5.order_check({"action": 1}) is not None
    assert mt5.copy_rates_from("XAUUSD", timeframe=60) is not None
    assert calls == [("args", {"action": 1}), ("kwargs", "XAUUSD", 60)]


def _fake_mt5_with_ticks(ticks):
    """Fake MT5 whose symbol_info_tick returns each tick in turn, then the last."""
    calls = {"n": 0}

    class Fake:
        def symbol_select(self, symbol, enable=True):
            return True

        def symbol_info_tick(self, symbol):
            tick = ticks[min(calls["n"], len(ticks) - 1)]
            calls["n"] += 1
            return tick

    return Fake(), calls


def test_refresh_server_offset_retries_until_a_fresh_quote(monkeypatch):
    # A symbol just added to Market Watch reports a stale quote before its first
    # fresh tick; derivation must poll past the stale ticks rather than give up.
    monkeypatch.delenv("MT5_SERVER_UTC_OFFSET_SECONDS", raising=False)
    monkeypatch.setenv("MT5_TIME_DERIVE_ATTEMPTS", "5")
    monkeypatch.setenv("MT5_TIME_DERIVE_DELAY", "0")
    set_derived_offset(None)

    now = int(time.time())
    ticks = [
        SimpleNamespace(time=now + 3 * 3600 - 5000),  # stale -> rejected
        SimpleNamespace(time=now + 3 * 3600 - 5000),  # stale -> rejected
        SimpleNamespace(time=now + 3 * 3600),  # fresh -> +3h
    ]
    fake, calls = _fake_mt5_with_ticks(ticks)
    monkeypatch.setattr(mt5_connection, "mt5", fake)

    mt5_connection.MT5Connection()._refresh_server_offset()

    assert resolve_offset_seconds() == 3 * 3600
    assert calls["n"] >= 3
    set_derived_offset(None)


def test_refresh_server_offset_stays_unresolved_without_a_fresh_quote(monkeypatch):
    # Market closed / no fresh quote: derivation exhausts its attempts and leaves
    # the offset unresolved (GTD then fails loud rather than guessing UTC).
    monkeypatch.delenv("MT5_SERVER_UTC_OFFSET_SECONDS", raising=False)
    monkeypatch.setenv("MT5_TIME_DERIVE_ATTEMPTS", "3")
    monkeypatch.setenv("MT5_TIME_DERIVE_DELAY", "0")
    set_derived_offset(None)

    now = int(time.time())
    stale = SimpleNamespace(time=now + 3 * 3600 - 5000)
    fake, calls = _fake_mt5_with_ticks([stale, stale, stale])
    monkeypatch.setattr(mt5_connection, "mt5", fake)

    mt5_connection.MT5Connection()._refresh_server_offset()

    assert resolve_offset_seconds() is None
    assert calls["n"] == 3
    set_derived_offset(None)
