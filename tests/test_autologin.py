import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from autologin import AutoLoginSettings, load_settings, render_start_ini, validate


def test_login_absent_means_disabled():
    s = load_settings({})
    assert s.enabled is False
    assert s.login == ""


def test_load_settings_reads_and_strips():
    s = load_settings(
        {
            "MT5_LOGIN": " 12345678 ",
            "MT5_PASSWORD": "example-password",
            "MT5_SERVER": " Exness-MT5Trial9 ",
        }
    )
    assert s.login == "12345678"
    assert s.server == "Exness-MT5Trial9"
    assert s.password == "example-password"
    assert s.enable_algo_trading is True
    assert s.enabled is True


def test_validate_rejects_login_without_server():
    with pytest.raises(ValueError, match="MT5_SERVER"):
        validate(AutoLoginSettings(login="1", password="p", server=""))


def test_validate_rejects_login_without_password():
    with pytest.raises(ValueError, match="MT5_PASSWORD"):
        validate(AutoLoginSettings(login="1", password="", server="s"))


def test_validate_allows_absent_creds():
    validate(load_settings({}))


def test_render_start_ini_has_login_block_and_autotrading():
    s = AutoLoginSettings(login="12345678", password="pw", server="Exness-MT5Trial9")
    ini = render_start_ini(s)
    assert "[Common]" in ini
    assert "Login=12345678" in ini
    assert "Password=pw" in ini
    assert "Server=Exness-MT5Trial9" in ini
    assert "[Experts]" in ini
    assert "AllowLiveTrading=1" in ini
    assert "Enabled=1" in ini
    assert "Account=1" in ini


@pytest.mark.parametrize("raw", ["0", "false", "False", "no", "off", "disabled"])
def test_render_start_ini_can_disable_autotrading(raw):
    s = load_settings(
        {
            "MT5_LOGIN": "12345678",
            "MT5_PASSWORD": "pw",
            "MT5_SERVER": "Exness-MT5Trial9",
            "MT5_ENABLE_ALGO_TRADING": raw,
        }
    )
    ini = render_start_ini(s)
    assert s.enable_algo_trading is False
    assert "AllowLiveTrading=0" in ini
    assert "Enabled=0" in ini
    assert "Account=0" in ini


def test_render_start_ini_defaults_autotrading_on():
    s = load_settings(
        {
            "MT5_LOGIN": "12345678",
            "MT5_PASSWORD": "pw",
            "MT5_SERVER": "Exness-MT5Trial9",
        }
    )
    assert s.enable_algo_trading is True
    assert "AllowLiveTrading=1" in render_start_ini(s)


def test_render_start_ini_uses_crlf():
    ini = render_start_ini(AutoLoginSettings(login="1", password="p", server="s"))
    assert "\r\n" in ini and ini.endswith("\r\n")
