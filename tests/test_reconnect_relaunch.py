"""Reconnects after the terminal dies: credentials, session marker, back-off.

Build 6230 incident (2026-10-06): the boot login loop killed the terminal the
API was attached to; the API's credential-less ``initialize()`` then launched a
terminal that never logged in, and every request started another reconnect.
"""

import sys
import types
from types import SimpleNamespace

import pytest

import mt5_connection
from autologin import session_attached


class _RelaunchingMT5:
    """Fake MT5 whose initialize() records its kwargs and succeeds on demand."""

    def __init__(self, succeed=True, login=476422618):
        self.initialize_calls = []
        self._succeed = succeed
        self._login = login

    def initialize(self, **kwargs):
        self.initialize_calls.append(kwargs)
        return self._succeed

    def account_info(self):
        return SimpleNamespace(login=self._login, server="Exness-MT5Trial9")

    def last_error(self):
        return (-10005, "IPC timeout")

    def symbols_get(self):
        return []

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info_tick(self, symbol):
        return None


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("MT5_LOGIN", "476422618")
    monkeypatch.setenv("MT5_PASSWORD", "example-password")
    monkeypatch.setenv("MT5_SERVER", "Exness-MT5Trial9")
    monkeypatch.setenv("MT5_RECONNECT_ATTEMPTS", "1")
    monkeypatch.setenv("MT5_TIME_DERIVE_ATTEMPTS", "1")
    monkeypatch.setenv("MT5_TIME_REFRESH_SECONDS", "0")
    monkeypatch.setenv("MT5_SESSION_MARKER", str(tmp_path / "session"))
    monkeypatch.setenv("MT5_LOGIN_SERVER_FILE", str(tmp_path / "login-server"))
    monkeypatch.setitem(
        sys.modules,
        "reconciliation",
        types.SimpleNamespace(reconcile=lambda: None),
    )
    return tmp_path


def _disconnected(monkeypatch, fake):
    monkeypatch.setattr(mt5_connection, "mt5", fake)
    return mt5_connection.MT5Connection()


def test_reconnect_logs_a_relaunched_terminal_in(monkeypatch, env):
    fake = _RelaunchingMT5()
    conn = _disconnected(monkeypatch, fake)

    assert conn.ensure_connection() is True

    assert fake.initialize_calls == [
        {
            "login": 476422618,
            "password": "example-password",
            "server": "Exness-MT5Trial9",
        }
    ]


def test_reconnect_uses_the_address_that_authorized_at_boot(monkeypatch, env):
    (env / "login-server").write_text("13.247.140.197:443\n")
    fake = _RelaunchingMT5()
    conn = _disconnected(monkeypatch, fake)

    assert conn.ensure_connection() is True

    assert fake.initialize_calls[0]["server"] == "13.247.140.197:443"


def test_boot_attach_passes_no_credentials(monkeypatch, env):
    fake = _RelaunchingMT5()
    conn = _disconnected(monkeypatch, fake)

    assert conn.initialize() is True

    assert fake.initialize_calls == [{}]


def test_attaching_writes_the_session_marker_the_login_loop_reads(monkeypatch, env):
    fake = _RelaunchingMT5()
    conn = _disconnected(monkeypatch, fake)

    assert conn.initialize() is True

    assert session_attached(env / "session", "476422618", since=0.0)
    assert not session_attached(env / "session", "1", since=0.0)


def test_failed_reconnect_backs_off_instead_of_retrying_per_request(monkeypatch, env):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(mt5_connection.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(mt5_connection.time, "sleep", lambda _s: None)
    monkeypatch.setenv("MT5_RECONNECT_COOLDOWN_SECONDS", "5")
    fake = _RelaunchingMT5(succeed=False)
    conn = _disconnected(monkeypatch, fake)

    for _ in range(20):
        assert conn.ensure_connection() is False
    assert len(fake.initialize_calls) == 1

    clock.now += 5.1
    assert conn.ensure_connection() is False
    assert len(fake.initialize_calls) == 2

    # The window doubles after each failure.
    clock.now += 5.1
    assert conn.ensure_connection() is False
    assert len(fake.initialize_calls) == 2
    clock.now += 5.0
    assert conn.ensure_connection() is False
    assert len(fake.initialize_calls) == 3


def test_successful_reconnect_clears_the_back_off(monkeypatch, env):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(mt5_connection.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(mt5_connection.time, "sleep", lambda _s: None)
    fake = _RelaunchingMT5(succeed=False)
    conn = _disconnected(monkeypatch, fake)
    assert conn.ensure_connection() is False

    clock.now += 60
    fake._succeed = True
    assert conn.ensure_connection() is True
    conn._set_status(mt5_connection.ConnectionStatus.DISCONNECTED)
    fake._succeed = False

    assert conn.ensure_connection() is False
    assert len(fake.initialize_calls) == 3
