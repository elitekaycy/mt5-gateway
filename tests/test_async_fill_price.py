"""Async-fill price confirmation: some servers (dealer-desk execution, e.g.
The5ers' FivePercentOnline) return TRADE_RETCODE_DONE with price 0.0 and the
real fill materializes in the deal/position moments later. The endpoint must
report the true fill price (bounded wait) instead of relaying a 0.0 every
consumer would mis-book. Observed live 2026-08-31; see qkt#1092 for the
consumer-side fault a raw 0.0 causes."""

from collections import namedtuple
from types import SimpleNamespace

import pytest
from flask import Flask

import routes.order as order_route
from idempotency import IdempotencyStore
from mt5_connection import MT5Connection

OrderResult = namedtuple("OrderResult", "retcode comment volume price order deal sl tp")
CheckResult = namedtuple("CheckResult", "retcode comment")


class _Record:
    def __init__(self, **fields):
        self._fields = fields

    def _asdict(self):
        return dict(self._fields)


@pytest.fixture
def client(monkeypatch):
    connection = SimpleNamespace(ensure_connection=lambda: True)
    monkeypatch.setattr(
        MT5Connection, "get_instance", classmethod(lambda cls: connection)
    )
    monkeypatch.setattr(order_route, "idempotency_store", IdempotencyStore())
    monkeypatch.setattr(
        order_route.mt5, "symbol_select", lambda *_: True, raising=False
    )
    monkeypatch.setattr(
        order_route.mt5,
        "symbol_info",
        lambda *_: SimpleNamespace(
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            digits=5,
            trade_tick_size=0.00001,
            filling_mode=2,
            trade_freeze_level=0,
            point=0.00001,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        order_route.mt5,
        "symbol_info_tick",
        lambda *_: SimpleNamespace(bid=1.09, ask=1.10),
        raising=False,
    )
    monkeypatch.setattr(order_route.mt5, "last_error", lambda: (0, "ok"), raising=False)
    monkeypatch.setattr(
        order_route.mt5,
        "order_check",
        lambda _: CheckResult(0, "valid"),
        raising=False,
    )
    # collapse the confirmation window so tests never actually wait
    monkeypatch.setattr(order_route, "FILL_CONFIRM_TIMEOUT_MS", 40)
    monkeypatch.setattr(order_route, "FILL_CONFIRM_POLL_MS", 1)

    app = Flask(__name__)
    app.register_blueprint(order_route.order_bp)
    return app.test_client()


def _send(client):
    return client.post("/order", json={"symbol": "EURUSD", "volume": 0.1, "type": "BUY"})


def test_sync_fill_price_passes_through_untouched(client, monkeypatch):
    lookups = []
    monkeypatch.setattr(
        order_route.mt5,
        "order_send",
        lambda _: OrderResult(10009, "done", 0.1, 1.10, 10, 11, 0, 0),
        raising=False,
    )
    monkeypatch.setattr(
        order_route.mt5,
        "history_deals_get",
        lambda **kw: lookups.append(kw),
        raising=False,
    )
    body = _send(client).get_json()
    assert body["result"]["price"] == 1.10
    assert body["fill_price_source"] == "order_send"
    assert lookups == []


def test_zero_price_resolves_from_the_deal(client, monkeypatch):
    monkeypatch.setattr(
        order_route.mt5,
        "order_send",
        lambda _: OrderResult(10009, "done", 0.0, 0.0, 10, 11, 0, 0),
        raising=False,
    )
    monkeypatch.setattr(
        order_route.mt5,
        "history_deals_get",
        lambda **kw: [_Record(price=1.1052, volume=0.1)] if kw.get("ticket") == 11 else [],
        raising=False,
    )
    body = _send(client).get_json()
    assert body["result"]["price"] == 1.1052
    assert body["result"]["volume"] == 0.1
    assert body["fill_price_source"] == "deal"


def test_zero_price_falls_back_to_the_position(client, monkeypatch):
    monkeypatch.setattr(
        order_route.mt5,
        "order_send",
        lambda _: OrderResult(10009, "done", 0.1, 0.0, 10, 0, 0, 0),
        raising=False,
    )
    monkeypatch.setattr(
        order_route.mt5, "history_deals_get", lambda **kw: [], raising=False
    )
    monkeypatch.setattr(
        order_route.mt5,
        "positions_get",
        lambda **kw: [_Record(price_open=1.1049)] if kw.get("ticket") == 10 else [],
        raising=False,
    )
    body = _send(client).get_json()
    assert body["result"]["price"] == 1.1049
    assert body["fill_price_source"] == "position"


def test_unresolved_price_is_relayed_raw_and_labeled(client, monkeypatch):
    monkeypatch.setattr(
        order_route.mt5,
        "order_send",
        lambda _: OrderResult(10009, "done", 0.1, 0.0, 10, 11, 0, 0),
        raising=False,
    )
    monkeypatch.setattr(
        order_route.mt5, "history_deals_get", lambda **kw: [], raising=False
    )
    monkeypatch.setattr(
        order_route.mt5, "positions_get", lambda **kw: [], raising=False
    )
    response = _send(client)
    body = response.get_json()
    assert response.status_code == 200
    assert body["result"]["price"] == 0.0
    assert body["fill_price_source"] == "unresolved"
