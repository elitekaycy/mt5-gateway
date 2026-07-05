import threading
from collections import namedtuple

from flask import Flask

import reconciliation
from kill_switch import KillSwitch
from metrics import Metrics
from mt5_connection import ConnectionStatus, MT5Connection
from security import install_security_hooks


def test_kill_switch_persists_across_instances(tmp_path):
    path = tmp_path / "kill"
    first = KillSwitch(path)
    first.engage()

    assert KillSwitch(path).is_active()

    KillSwitch(path).release()
    assert not first.is_active()


def test_auth_and_kill_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("API_KEY", "secret")
    import security

    monkeypatch.setattr(security, "kill_switch", KillSwitch(tmp_path / "kill"))
    app = Flask(__name__)
    install_security_hooks(app)
    app.add_url_rule(
        "/order", endpoint="order", view_func=lambda: {"ok": True}, methods=["POST"]
    )
    app.add_url_rule(
        "/health/live",
        endpoint="live",
        view_func=lambda: {"status": "alive"},
    )
    client = app.test_client()

    assert client.post("/order").status_code == 401
    assert client.get("/health/live").status_code == 200
    assert client.get("/apidocs/").status_code == 404
    assert client.get("/apispec_1.json").status_code == 404
    assert client.get("/flasgger_static/swagger-ui.css").status_code == 404
    assert (
        client.post("/order", headers={"Authorization": "Bearer secret"}).status_code
        == 200
    )

    security.kill_switch.engage()
    assert (
        client.post("/order", headers={"Authorization": "Bearer secret"}).status_code
        == 423
    )


def test_reconciliation_filters_magic(monkeypatch):
    Item = namedtuple("Item", "ticket magic")
    monkeypatch.setattr(
        reconciliation.mt5,
        "positions_get",
        lambda: (Item(1, 7), Item(2, 8)),
        raising=False,
    )
    monkeypatch.setattr(
        reconciliation.mt5, "orders_get", lambda: (Item(3, 7),), raising=False
    )
    monkeypatch.setattr(
        reconciliation.mt5,
        "history_deals_get",
        lambda *_: (Item(4, 7),),
        raising=False,
    )

    snapshot = reconciliation.reconcile(magic=7)

    assert [item["ticket"] for item in snapshot["positions"]] == [1]
    assert [item["ticket"] for item in snapshot["orders"]] == [3]
    assert [item["ticket"] for item in snapshot["deals"]] == [4]


def test_reconnect_is_single_flight(monkeypatch):
    connection = MT5Connection()
    connection._status = ConnectionStatus.DISCONNECTED
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def initialize():
        calls.append(1)
        entered.set()
        release.wait(timeout=1)
        connection._status = ConnectionStatus.CONNECTED
        return True

    monkeypatch.setattr(connection, "initialize", initialize)
    monkeypatch.setattr(reconciliation, "reconcile", lambda: {})
    results = []
    first = threading.Thread(
        target=lambda: results.append(connection.ensure_connection())
    )
    first.start()
    entered.wait(timeout=1)

    assert connection.ensure_connection() is False

    release.set()
    first.join()
    assert calls == [1]
    assert results == [True]


def test_metrics_render_prometheus_labels():
    registry = Metrics()
    registry.inc("orders_submitted_total", (("symbol", "EURUSD"), ("side", "BUY")))

    rendered = registry.render()

    assert 'orders_submitted_total{side="BUY",symbol="EURUSD"} 1.0' in rendered
