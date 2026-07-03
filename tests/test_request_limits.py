from datetime import datetime, timedelta, timezone

import pytest
from request_limits import (
    validate_date_range,
    validate_num_bars,
    validate_tick_flags,
)


def test_num_bars_is_bounded(monkeypatch):
    monkeypatch.setenv("MAX_NUM_BARS", "100")
    assert validate_num_bars(100) == 100
    with pytest.raises(ValueError):
        validate_num_bars(101)


def test_date_range_is_bounded(monkeypatch):
    monkeypatch.setenv("MAX_HISTORY_RANGE_DAYS", "7")
    start = datetime.now(timezone.utc)
    validate_date_range(start, start + timedelta(days=7))
    with pytest.raises(ValueError):
        validate_date_range(start, start + timedelta(days=8))


def test_tick_flags_are_bounded():
    assert validate_tick_flags(7) == 7
    with pytest.raises(ValueError):
        validate_tick_flags(8)
