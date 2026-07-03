from collections import namedtuple

import lib

Deal = namedtuple(
    "Deal",
    "ticket time time_msc entry symbol type volume price profit commission swap comment",
)


def test_closed_position_aggregates_all_deals(monkeypatch):
    deals = (
        Deal(1, 100, 0, 0, "EURUSD", 0, 1.0, 1.10, 0, -2, 0, "open"),
        Deal(2, 200, 0, 1, "EURUSD", 1, 0.4, 1.11, 40, -1, -0.5, "close 1"),
        Deal(3, 300, 0, 1, "EURUSD", 1, 0.6, 1.12, 60, -1, -0.5, "close 2"),
    )
    monkeypatch.setattr(lib.mt5, "history_deals_get", lambda **_: deals, raising=False)

    result = lib.get_deal_from_ticket(42)

    assert result["closed"] is True
    assert result["open_price"] == 1.10
    assert result["close_price"] == 1.12
    assert result["profit"] == 100
    assert result["commission"] == -4
    assert result["swap"] == -1


def test_open_position_has_no_fabricated_close(monkeypatch):
    deals = (Deal(1, 100, 0, 0, "EURUSD", 0, 1.0, 1.10, 0, -2, 0, "open"),)
    monkeypatch.setattr(lib.mt5, "history_deals_get", lambda **_: deals, raising=False)

    result = lib.get_deal_from_ticket(42)

    assert result["closed"] is False
    assert result["close_time"] is None
    assert result["close_price"] is None
