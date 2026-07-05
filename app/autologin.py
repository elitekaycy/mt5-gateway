"""Headless env-driven MT5 login policy.

Pure module: NO MetaTrader5 import, so it runs under host pytest. It decides
*what* to do (is login enabled, what startup ini); the boot script performs the
MT5-coupled mechanism (seed servers.dat, launch the terminal with the ini).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AutoLoginSettings:
    login: str
    password: str
    server: str
    enable_algo_trading: bool = True

    @property
    def enabled(self) -> bool:
        """True when env-login should be attempted (a login number is present)."""
        return bool(self.login)


def load_settings(env) -> AutoLoginSettings:
    """Build settings from an environ-like mapping, e.g. load_settings(os.environ)."""
    return AutoLoginSettings(
        login=env.get("MT5_LOGIN", "").strip(),
        password=env.get("MT5_PASSWORD", ""),
        server=env.get("MT5_SERVER", "").strip(),
        enable_algo_trading=_bool_env(env.get("MT5_ENABLE_ALGO_TRADING"), default=True),
    )


def _bool_env(value: Optional[str], *, default: bool) -> bool:
    """Parse a docker-friendly boolean env value."""
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def validate(s: AutoLoginSettings) -> None:
    """Raise ValueError on an unusable config. Absent login is valid (no env-login)."""
    if s.login and not s.server:
        raise ValueError("MT5_LOGIN set but MT5_SERVER is empty")
    if s.login and not s.password:
        raise ValueError("MT5_LOGIN set but MT5_PASSWORD is empty")


def render_start_ini(s: AutoLoginSettings) -> str:
    r"""Render an MT5 startup-config ini that auto-logs-in and enables algo trading.

    Passed to the terminal as ``terminal64.exe /config:<file>``. e.g. login 123 on
    Exness-MT5Trial9 -> "[Common]\r\nLogin=123\r\nServer=Exness-MT5Trial9...".
    Windows CRLF — MT5 parses the config as a Windows ini.
    """
    algo_enabled = "1" if s.enable_algo_trading else "0"
    lines = [
        "[Common]",
        f"Login={s.login}",
        f"Password={s.password}",
        f"Server={s.server}",
        "",
        "[Experts]",
        f"AllowLiveTrading={algo_enabled}",
        f"Enabled={algo_enabled}",
        f"Account={algo_enabled}",
    ]
    return "\r\n".join(lines) + "\r\n"
