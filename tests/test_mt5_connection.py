import threading
import time
from types import SimpleNamespace

from mt5_connection import SerializedMT5


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
