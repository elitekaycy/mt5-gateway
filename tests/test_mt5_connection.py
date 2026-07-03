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
