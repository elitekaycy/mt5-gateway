#!/usr/bin/env python3
"""Acceptance test for one gateway image: real container, real demo account.

Boots the image on a fresh or supplied /config, logs in, places and closes one
minimum-size order, then checks that it survives a restart and a terminal crash.
It refuses to trade unless the broker reports a demo account.

    scripts/test-image-variant.py --image mt5-gateway:test --variant headless \
        --env-file .env --symbol BTCUSDm
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEMO_TRADE_MODE = 0
READY_TIMEOUT_S = 600
RECOVERY_TIMEOUT_S = 300
TRANSIENT_RETRY_S = 120
RECONCILE_S = 8


class Check(Exception):
    """A failed acceptance check."""


def docker(*args: str, check: bool = True) -> str:
    done = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and done.returncode != 0:
        raise Check(f"docker {args[0]} failed: {done.stderr.strip()[:300]}")
    return done.stdout


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


class Gateway:
    """A running container and its API."""

    def __init__(self, args: argparse.Namespace, env: dict[str, str]) -> None:
        self.args = args
        self.env = env
        self.name = f"mt5-variant-test-{uuid.uuid4().hex[:8]}"
        self.base = f"http://127.0.0.1:{args.port}"
        self.trade_log: list[dict[str, Any]] = []

    def start(self) -> None:
        docker(
            "run", "-d", "--name", self.name, "--env-file", str(self.args.env_file),
            "-p", f"127.0.0.1:{self.args.port}:5001", "-v", f"{self.args.config}:/config",
            self.args.image,
        )  # fmt: skip

    def remove(self) -> None:
        docker("rm", "-f", self.name, check=False)

    def exec(self, *cmd: str, check: bool = True) -> str:
        return docker("exec", self.name, *cmd, check=check)

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        status, reply = self._request(method, path, body)
        if method == "POST":
            self.trade_log.append(
                {"at": time.time(), "path": path, "status": status, "reply": reply}
            )
        return status, reply

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        headers = {"Content-Type": "application/json"}
        if self.env.get("API_KEY"):
            headers["Authorization"] = f"Bearer {self.env['API_KEY']}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(  # noqa: S310
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            payload = error.read()
            try:
                return error.code, json.loads(payload)
            except ValueError:
                return error.code, payload.decode(errors="replace")[:300]
        except (OSError, ValueError) as error:
            return 0, str(error)

    def wait_ready(self, timeout: int) -> float:
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            if self.request("GET", "/health/ready")[0] == 200:
                return time.monotonic() - started
            time.sleep(3)
        raise Check(f"not ready after {timeout}s")

    def account(self) -> dict[str, Any]:
        status, body = self.request("GET", "/account")
        if status != 200:
            raise Check(f"/account returned {status}: {body}")
        return body.get("data", body) if isinstance(body, dict) else {}

    def assert_logged_in(self) -> dict[str, Any]:
        # Readiness can precede the session settling after a relaunch.
        deadline = time.monotonic() + 120
        account: dict[str, Any] = {}
        while time.monotonic() < deadline:
            account = self.account()
            if str(account.get("login")) == self.env["MT5_LOGIN"]:
                return account
            time.sleep(3)
        raise Check(f"logged in as {account.get('login')}, not the configured login")


def wait_recovered(gw: Gateway) -> None:
    """Waits for the session to return after a crash.

    /health/ready only reports state. Reconnecting happens on API calls, as it does
    for a real client, so this polls /account.
    """
    deadline = time.monotonic() + RECOVERY_TIMEOUT_S
    while time.monotonic() < deadline:
        status, body = gw.request("GET", "/account")
        account = body.get("data", body) if isinstance(body, dict) else {}
        if status == 200 and str(account.get("login")) == gw.env["MT5_LOGIN"]:
            return
        time.sleep(5)
    raise Check(f"session not back after {RECOVERY_TIMEOUT_S}s")


def check_boot(gw: Gateway, evidence: dict[str, Any]) -> None:
    evidence["boot_ready_seconds"] = round(gw.wait_ready(READY_TIMEOUT_S))
    account = gw.assert_logged_in()
    if not (account.get("trade_allowed") and account.get("trade_expert")):
        raise Check("algo trading is not enabled on the logged-in session")
    evidence["server"] = account.get("server")


def check_market_data(gw: Gateway, evidence: dict[str, Any]) -> None:
    symbol = gw.args.symbol
    status, tick = gw.request("GET", f"/symbol_info_tick/{symbol}")
    if status != 200:
        raise Check(f"tick returned {status}: {tick}")
    status, bars = gw.request(
        "GET", f"/fetch_data_pos?symbol={symbol}&timeframe=M1&num_bars=50"
    )
    if status != 200 or not bars:
        raise Check(f"bars returned {status}: {str(bars)[:200]}")
    evidence["bars_returned"] = (
        len(bars.get("data", bars)) if isinstance(bars, dict) else len(bars)
    )


def _positions(gw: Gateway, magic: int) -> list[dict[str, Any]]:
    status, body = gw.request("GET", f"/get_positions?magic={magic}")
    if status not in (200, 404):
        raise Check(f"/get_positions returned {status}: {body}")
    rows = body.get("data", body) if isinstance(body, dict) else body
    rows = (
        rows
        if isinstance(rows, list)
        else rows.get("positions", [])
        if isinstance(rows, dict)
        else []
    )
    return [row for row in rows if row.get("magic") == magic]


def _is_transient(reply: Any) -> bool:
    return isinstance(reply, dict) and reply.get("error_type") in (
        "retryable",
        "unknown_outcome",
    )


def _settled(gw: Gateway, seconds: int, done: Any) -> bool:
    """Broker truth decides what an unclear reply meant, e.g. 10031 can still execute."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if done():
            return True
        time.sleep(1)
    return bool(done())


def _send_order(
    gw: Gateway, order: dict[str, Any], evidence: dict[str, Any]
) -> tuple[int, Any]:
    """Sends an order, reconciling before any retry so it cannot open two positions."""
    magic = order["magic"]
    opened = lambda: _positions(gw, magic)  # noqa: E731
    deadline = time.monotonic() + TRANSIENT_RETRY_S
    while True:
        status, reply = gw.request("POST", "/order", order)
        if not _is_transient(reply):
            return status, reply
        if _settled(gw, RECONCILE_S, opened):
            evidence["unclear_order_executed"] = (
                evidence.get("unclear_order_executed", 0) + 1
            )
            return 200, reply
        evidence["unclear_order_not_executed"] = (
            evidence.get("unclear_order_not_executed", 0) + 1
        )
        if time.monotonic() > deadline:
            return status, reply
        order = {**order, "client_order_id": uuid.uuid4().hex}


def _close(
    gw: Gateway, magic: int, ticket: int, evidence: dict[str, Any]
) -> tuple[int, Any]:
    """Closes a position, reconciling before any retry."""
    deadline = time.monotonic() + TRANSIENT_RETRY_S
    gone = lambda: not any(p["ticket"] == ticket for p in _positions(gw, magic))  # noqa: E731
    while True:
        status, reply = gw.request(
            "POST", "/close_position", {"position": {"ticket": ticket}}
        )
        if not _is_transient(reply):
            return status, reply
        if _settled(gw, RECONCILE_S, gone):
            evidence["unclear_close_executed"] = (
                evidence.get("unclear_close_executed", 0) + 1
            )
            return 200, reply
        evidence["unclear_close_not_executed"] = (
            evidence.get("unclear_close_not_executed", 0) + 1
        )
        if time.monotonic() > deadline:
            return status, reply


def _flatten(gw: Gateway, magic: int) -> None:
    for position in _positions(gw, magic):
        _close(gw, magic, position["ticket"], {})


def check_trade_round_trip(gw: Gateway, evidence: dict[str, Any]) -> None:
    account = gw.account()
    if account.get("trade_mode") != DEMO_TRADE_MODE:
        raise Check(
            f"refusing to trade: trade_mode={account.get('trade_mode')} is not demo"
        )
    magic = 700000 + int(time.time()) % 99999
    order = {
        "symbol": gw.args.symbol,
        "volume": gw.args.lots,
        "type": "BUY",
        "magic": magic,
        "comment": "variant-test",
        "client_order_id": uuid.uuid4().hex,
    }
    try:
        status, sent = _send_order(gw, order, evidence)
        if status != 200:
            raise Check(f"/order returned {status}: {sent}")
        time.sleep(2)
        positions = _positions(gw, magic)
        if len(positions) != 1 or float(positions[0]["volume"]) != gw.args.lots:
            raise Check(f"expected one {gw.args.lots} position, got {positions}")
        ticket = positions[0]["ticket"]
        status, closed = _close(gw, magic, ticket, evidence)
        if status != 200:
            raise Check(f"/close_position returned {status}: {closed}")
        time.sleep(2)
        if _positions(gw, magic):
            raise Check(f"position {ticket} still open after close")
        evidence.setdefault("trade_tickets", []).append(ticket)
    finally:
        _flatten(gw, magic)
        if _positions(gw, magic):
            print(f"WARNING: magic {magic} still has an open demo position", flush=True)


def check_restart(gw: Gateway, evidence: dict[str, Any]) -> None:
    started = time.monotonic()
    docker("restart", "-t", "20", gw.name)
    gw.wait_ready(RECOVERY_TIMEOUT_S)
    gw.assert_logged_in()
    evidence["restart_ready_seconds"] = round(time.monotonic() - started)


def check_terminal_crash(gw: Gateway, evidence: dict[str, Any]) -> None:
    gw.exec("pkill", "-9", "-f", "terminal64.exe")
    started = time.monotonic()
    time.sleep(5)
    wait_recovered(gw)
    evidence["terminal_crash_recovery_seconds"] = round(time.monotonic() - started)


def record_trading_gap_after_terminal_crash(
    gw: Gateway, evidence: dict[str, Any]
) -> None:
    """For images older than the fix: they reject orders with 10027 here. Records it."""
    magic = 700000 + int(time.time()) % 99999
    order = {
        "symbol": gw.args.symbol,
        "volume": gw.args.lots,
        "type": "BUY",
        "magic": magic,
        "comment": "variant-test",
        "client_order_id": uuid.uuid4().hex,
    }
    status, reply = _send_order(gw, order, evidence)
    retcode = (
        reply.get("mt5_error", {}).get("retcode") if isinstance(reply, dict) else None
    )
    evidence["order_after_terminal_crash"] = {"status": status, "retcode": retcode}
    _flatten(gw, magic)


def check_api_crash(gw: Gateway, evidence: dict[str, Any]) -> None:
    gw.exec("pkill", "-9", "-f", "waitress")
    started = time.monotonic()
    time.sleep(5)
    wait_recovered(gw)
    evidence["api_crash_recovery_seconds"] = round(time.monotonic() - started)


def check_variant_surface(gw: Gateway, evidence: dict[str, Any]) -> None:
    processes = gw.exec("ps", "-eo", "comm")
    desktop = [name for name in ("Xvnc", "nginx", "openbox") if name in processes]
    if gw.args.variant == "headless":
        if desktop:
            raise Check(f"headless image is running desktop processes: {desktop}")
        if "Xvfb" not in processes:
            raise Check("Xvfb is not running")
    else:
        if len(desktop) != 3:
            raise Check(f"VNC desktop is incomplete, running only: {desktop}")
        code = gw.exec(
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "http://localhost:3000/",
            check=False,
        )
        if code not in ("200", "401"):
            raise Check(f"VNC web port answered {code}")
        evidence["vnc_http_status"] = code


def check_no_secret_on_disk_or_logs(gw: Gateway, evidence: dict[str, Any]) -> None:
    password = gw.env["MT5_PASSWORD"]
    logs = subprocess.run(["docker", "logs", gw.name], capture_output=True, text=True)
    if password in logs.stdout or password in logs.stderr:
        raise Check("the broker password appears in the container logs")
    # 04-install-mt5.sh shreds it a few seconds after the login loop finishes.
    ini = "/config/.wine/drive_c/start.ini"
    deadline = time.monotonic() + 120
    while _exists(gw, ini) and time.monotonic() < deadline:
        time.sleep(3)
    if _exists(gw, ini):
        raise Check("start.ini with the password is still on the volume after 120s")
    evidence["secrets_clean"] = True


def _exists(gw: Gateway, path: str) -> bool:
    probe = ["docker", "exec", gw.name, "test", "-e", path]
    return subprocess.run(probe, capture_output=True).returncode == 0


def check_graceful_stop(gw: Gateway, evidence: dict[str, Any]) -> None:
    started = time.monotonic()
    docker("stop", "-t", "30", gw.name)
    evidence["stop_seconds"] = round(time.monotonic() - started)
    if evidence["stop_seconds"] >= 30:
        raise Check("the container ignored SIGTERM until the stop timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--variant", choices=["vnc", "headless"], required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--symbol", default="BTCUSDm")
    parser.add_argument(
        "--config", help="/config source; default is a fresh temporary volume"
    )
    parser.add_argument("--lots", type=float, default=0.01)
    parser.add_argument("--port", type=int, default=15001)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--keep-going", action="store_true", help="run later checks after a failure"
    )
    parser.add_argument("--no-crash-checks", action="store_true")
    parser.add_argument(
        "--older-image", action="store_true", help="the image predates the 10027 fix"
    )
    parser.add_argument(
        "--trade-rounds", type=int, default=1, help="order round trips right after boot"
    )
    args = parser.parse_args()
    # A timeout or Ctrl-C must still run the cleanup below.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    env = read_env_file(args.env_file)
    temporary = None
    if not args.config:
        temporary = f"mt5-variant-test-{uuid.uuid4().hex[:8]}"
        docker("volume", "create", temporary)
        args.config = temporary
    gw = Gateway(args, env)
    evidence: dict[str, Any] = {"image": args.image, "variant": args.variant}
    checks = [
        check_boot,
        check_variant_surface,
        check_market_data,
        *[check_trade_round_trip] * args.trade_rounds,
        check_no_secret_on_disk_or_logs,
    ]
    if not args.no_crash_checks:
        checks += [
            check_restart,
            check_terminal_crash,
            record_trading_gap_after_terminal_crash
            if args.older_image
            else check_trade_round_trip,
        ]
        if args.variant == "headless":
            checks.append(check_api_crash)
        checks += [check_restart, check_trade_round_trip]
    checks.append(check_graceful_stop)

    failures = []
    try:
        gw.start()
        for check in checks:
            try:
                check(gw, evidence)
                print(f"PASS {check.__name__}", flush=True)
            except Check as failure:
                print(f"FAIL {check.__name__}: {failure}", flush=True)
                failures.append(check.__name__)
                if not args.keep_going:
                    break
    finally:
        if args.evidence:
            full = subprocess.run(
                ["docker", "logs", gw.name], capture_output=True, text=True
            )
            scrubbed = (full.stdout + full.stderr).replace(
                env.get("MT5_PASSWORD", "\0"), "***"
            )
            args.evidence.with_suffix(".container.log").write_text(scrubbed)
        if failures:
            tail = subprocess.run(
                ["docker", "logs", "--tail", "25", gw.name],
                capture_output=True,
                text=True,
            )
            print(
                (tail.stdout + tail.stderr).replace(
                    env.get("MT5_PASSWORD", "\0"), "***"
                )[-3000:]
            )
        gw.remove()
        if temporary:
            docker("volume", "rm", temporary, check=False)
    evidence["failures"] = failures
    evidence["trade_log"] = gw.trade_log
    print(json.dumps(evidence, indent=2))
    if args.evidence:
        args.evidence.write_text(json.dumps(evidence, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
