"""Readiness reflects MT5 availability only; the kill switch is reported, not a fault."""

from types import SimpleNamespace

import pytest
from flask import Flask

import routes.health as health_route
from kill_switch import KillSwitch


class _Connection:
    def __init__(self, connected):
        self._connected = connected

    def is_connected(self):
        return self._connected

    def get_status(self):
        return SimpleNamespace(value="connected" if self._connected else "disconnected")

    def get_last_error(self):
        return None if self._connected else "terminal down"


@pytest.fixture
def make_client(monkeypatch, tmp_path):
    def _make(connected=True, kill_engaged=False):
        connection = _Connection(connected)
        monkeypatch.setattr(
            health_route.MT5Connection,
            "get_instance",
            classmethod(lambda cls: connection),
        )
        monkeypatch.setattr(
            health_route.mt5, "terminal_info", lambda: SimpleNamespace(), raising=False
        )
        monkeypatch.setattr(
            health_route.mt5, "account_info", lambda: SimpleNamespace(), raising=False
        )
        switch = KillSwitch(tmp_path / "kill-switch")
        if kill_engaged:
            switch.engage()
        monkeypatch.setattr(health_route, "kill_switch", switch)
        app = Flask(__name__)
        app.register_blueprint(health_route.health_bp)
        return app.test_client()

    return _make


def test_ready_when_connected_and_kill_switch_released(make_client):
    response = make_client(connected=True, kill_engaged=False).get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ready",
        "mt5_status": "connected",
        "kill_switch_active": False,
    }


def test_ready_stays_200_while_kill_switch_is_engaged(make_client):
    """An engaged kill switch is a trading gate the gateway keeps serving through
    (reads, flatten, release), so it must not flip readiness: compose
    `service_healthy` dependants could not restart during a weekend kill."""
    response = make_client(connected=True, kill_engaged=True).get("/health/ready")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ready"
    assert body["kill_switch_active"] is True


def test_not_ready_when_mt5_is_disconnected(make_client):
    response = make_client(connected=False, kill_engaged=False).get("/health/ready")

    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "not_ready"
    assert body["mt5_status"] == "disconnected"
    assert body["error"] == "terminal down"
    assert body["kill_switch_active"] is False
