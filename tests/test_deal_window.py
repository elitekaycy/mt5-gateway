import pytest
from deal_window import DealWindowError, parse_deal_window


def test_range_only_returns_none_position():
    from_ts, to_ts, position = parse_deal_window(
        {"from_date": "2026-05-13", "to_date": "2026-06-13"}
    )
    assert from_ts < to_ts
    assert position is None


def test_position_is_parsed_when_present():
    _, _, position = parse_deal_window(
        {"from_date": "2026-05-13", "to_date": "2026-06-13", "position": "123"}
    )
    assert position == 123


def test_missing_dates_raise():
    with pytest.raises(DealWindowError, match="from_date and to_date"):
        parse_deal_window({"from_date": "2026-05-13"})


def test_bad_date_format_raises():
    with pytest.raises(DealWindowError, match="Invalid parameter format"):
        parse_deal_window({"from_date": "not-a-date", "to_date": "2026-06-13"})


def test_bad_position_raises():
    with pytest.raises(DealWindowError, match="Invalid parameter format"):
        parse_deal_window(
            {"from_date": "2026-05-13", "to_date": "2026-06-13", "position": "abc"}
        )


def test_inverted_range_raises():
    with pytest.raises(DealWindowError, match="before"):
        parse_deal_window({"from_date": "2026-06-13", "to_date": "2026-05-13"})


def test_zulu_suffix_is_accepted():
    from_ts, to_ts, _ = parse_deal_window(
        {"from_date": "2026-05-13T00:00:00Z", "to_date": "2026-06-13T00:00:00Z"}
    )
    assert to_ts - from_ts == 31 * 24 * 3600
