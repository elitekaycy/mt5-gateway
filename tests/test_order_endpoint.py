from collections import namedtuple
from types import SimpleNamespace

import pytest
import routes.order as order_route
from flask import Flask
from idempotency import IdempotencyStore
from mt5_connection import MT5Connection

OrderResult = namedtuple("OrderResult", "retcode comment volume price order deal sl tp")
CheckResult = namedtuple("CheckResult", "retcode comment")


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

    app = Flask(__name__)
    app.register_blueprint(order_route.order_bp)
    return app.test_client()


def test_duplicate_http_request_places_only_one_order(client, monkeypatch):
    calls = []

    def order_send(request):
        calls.append(request)
        return OrderResult(10009, "done", 0.1, 1.10, 10, 11, 0, 0)

    monkeypatch.setattr(order_route.mt5, "order_send", order_send, raising=False)
    payload = {"symbol": "EURUSD", "volume": 0.1, "type": "BUY"}
    headers = {"Idempotency-Key": "strategy-order-1"}

    first = client.post("/order", json=payload, headers=headers)
    second = client.post("/order", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.get_json() == first.get_json()
    assert len(calls) == 1
    assert calls[0]["magic"] != 0


def test_same_key_with_different_http_request_returns_conflict(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        order_route.mt5,
        "order_send",
        lambda request: (
            calls.append(request) or OrderResult(10009, "done", 0.1, 1.10, 10, 11, 0, 0)
        ),
        raising=False,
    )
    headers = {"Idempotency-Key": "strategy-order-1"}
    client.post(
        "/order",
        json={"symbol": "EURUSD", "volume": 0.1, "type": "BUY"},
        headers=headers,
    )

    response = client.post(
        "/order",
        json={"symbol": "EURUSD", "volume": 0.2, "type": "BUY"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.get_json()["error_type"] == "idempotency_conflict"
    assert len(calls) == 1


def test_placed_retcode_is_success(client, monkeypatch):
    monkeypatch.setattr(
        order_route.mt5,
        "order_send",
        lambda _: OrderResult(10008, "placed", 0.1, 1.10, 10, 0, 0, 0),
        raising=False,
    )

    response = client.post(
        "/order",
        json={"symbol": "EURUSD", "volume": 0.1, "type": "BUY"},
    )

    assert response.status_code == 200
    assert response.get_json()["state"] == "placed"


def test_none_outcome_is_ambiguous_and_replayed(client, monkeypatch):
    calls = []

    def order_send(request):
        calls.append(request)
        return None

    monkeypatch.setattr(order_route.mt5, "order_send", order_send, raising=False)
    payload = {"symbol": "EURUSD", "volume": 0.1, "type": "BUY"}
    headers = {"Idempotency-Key": "ambiguous-order"}

    first = client.post("/order", json=payload, headers=headers)
    second = client.post("/order", json=payload, headers=headers)

    assert first.status_code == 502
    assert first.get_json()["error_type"] == "unknown_outcome"
    assert second.status_code == 502
    assert len(calls) == 1
