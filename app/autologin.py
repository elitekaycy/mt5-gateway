"""Headless env-driven MT5 login policy.

Pure module: NO MetaTrader5 import, so it runs under host pytest. It decides
*what* to do (is login enabled, what startup ini); the boot script performs the
MT5-coupled mechanism (seed servers.dat, launch the terminal with the ini).
"""

from dataclasses import dataclass
from pathlib import Path
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


def authorization_count(log_dir: Path) -> int:
    """Count successful authorizations in retained MT5 terminal journals."""
    count = 0
    for log_path in log_dir.glob("*.log"):
        try:
            journal = log_path.read_text(encoding="utf-16-le", errors="ignore")
        except OSError:
            continue
        count += journal.lower().count("authorized on")
    return count


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


# The API (Wine Python) and the boot script (Linux) share these files through
# /tmp, which Wine maps as Z:\tmp. /tmp lives in the container layer, so a
# recreated container starts without them; the boot script also clears them.
SESSION_MARKER = "/tmp/mt5-api-session"  # noqa: S108 - container-private
LOGIN_SERVER_FILE = "/tmp/mt5-login-server"  # noqa: S108 - container-private


def wine_path(linux_path: str, nt: bool) -> str:
    r"""Return the path a process on this side of Wine opens, e.g. Z:\tmp\x on nt."""
    if not nt:
        return linux_path
    return "Z:" + linux_path.replace("/", "\\")


def write_session_marker(path: Path, login: str, now: float) -> None:
    """Record that the API holds an MT5 session logged in to ``login`` at ``now``.

    The boot login loop reads it: a terminal the API is attached to is
    authorized, whatever the journal says. Build 6230 can log in later than the
    loop's window and its ``authorized on`` line can land later still, so the
    journal alone made the loop kill a logged-in terminal under the API.
    """
    path.write_text(f"{login} {now:.3f}\n", encoding="ascii")


def session_attached(path: Path, login: str, since: float) -> bool:
    """True when the marker shows the API logged in to ``login`` at or after ``since``."""
    try:
        recorded_login, recorded_at = path.read_text(encoding="ascii").split()
        return recorded_login == login.strip() and float(recorded_at) >= since
    except (OSError, ValueError):
        return False


def reconnect_credentials(env, login_server: Optional[str]) -> dict:
    """Keyword arguments for ``mt5.initialize`` on a reconnect.

    When the terminal is gone, ``initialize()`` launches a fresh one. Without
    credentials that terminal never logs in (build 6230 keeps no usable saved
    login for a terminal started without the boot ini), so every later
    ``initialize()`` times out with IPC -10005 for as long as the process lives.
    With env-login configured the relaunched terminal is logged in with the
    server address that authorized at boot (``login_server``), else the
    configured server name. Without env-login there is nothing to pass.
    """
    settings = load_settings(env)
    if not settings.enabled or not settings.password:
        return {}
    try:
        login = int(settings.login)
    except ValueError:
        return {}
    server = (login_server or "").strip() or settings.server
    return {"login": login, "password": settings.password, "server": server}


def read_login_server(path: Path) -> Optional[str]:
    """The connect address that authorized at boot, or None when unknown."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None
