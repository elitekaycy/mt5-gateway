import threading

import pytest

import lib


@pytest.fixture(autouse=True)
def clear_symbol_cache():
    with lib._symbol_select_cache_lock:
        lib._symbol_select_cache.clear()
    yield
    with lib._symbol_select_cache_lock:
        lib._symbol_select_cache.clear()


def _stub_symbol_select(monkeypatch, result=True):
    calls = []

    def symbol_select(symbol, enable):
        calls.append((symbol, enable))
        return result

    monkeypatch.setattr(lib.mt5, "symbol_select", symbol_select, raising=False)
    return calls


def test_validate_symbol_caches_successful_select(monkeypatch):
    calls = _stub_symbol_select(monkeypatch)

    assert lib.validate_symbol("EURUSD") is True
    assert lib.validate_symbol("EURUSD") is True
    assert calls == [("EURUSD", True)]


def test_validate_symbol_does_not_cache_failures(monkeypatch):
    calls = _stub_symbol_select(monkeypatch, result=False)

    assert lib.validate_symbol("NOT_A_SYMBOL") is False
    assert lib.validate_symbol("NOT_A_SYMBOL") is False
    assert len(calls) == 2


def test_invalidate_symbol_forces_reselect(monkeypatch):
    calls = _stub_symbol_select(monkeypatch)

    assert lib.validate_symbol("EURUSD") is True
    lib.invalidate_symbol("EURUSD")
    assert lib.validate_symbol("EURUSD") is True
    assert calls == [("EURUSD", True), ("EURUSD", True)]


def test_invalidate_unknown_symbol_is_a_noop():
    lib.invalidate_symbol("NEVER_SEEN")


def test_cache_is_bounded_and_evicts_oldest(monkeypatch):
    calls = _stub_symbol_select(monkeypatch)
    monkeypatch.setattr(lib, "_SYMBOL_SELECT_CACHE_MAX_SIZE", 4)

    for index in range(4):
        assert lib.validate_symbol(f"SYM{index}") is True
    assert len(lib._symbol_select_cache) == 4

    assert lib.validate_symbol("SYM4") is True
    assert len(lib._symbol_select_cache) == 4
    assert "SYM0" not in lib._symbol_select_cache

    # Evicted symbol re-selects on next validation; cached ones do not.
    assert lib.validate_symbol("SYM1") is True
    assert lib.validate_symbol("SYM0") is True
    assert [symbol for symbol, _ in calls].count("SYM1") == 1
    assert [symbol for symbol, _ in calls].count("SYM0") == 2


def test_concurrent_first_select_converges_to_one_cache_entry(monkeypatch):
    calls = _stub_symbol_select(monkeypatch)
    barrier = threading.Barrier(12)

    def validate():
        barrier.wait()
        assert lib.validate_symbol("EURUSD") is True

    threads = [threading.Thread(target=validate) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # All threads saw a valid symbol; a small number of selects raced before
    # the first cache insert, but the cached steady state is one entry.
    assert len(calls) <= 12
    assert len(lib._symbol_select_cache) == 1
