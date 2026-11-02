#!/usr/bin/env python3
"""MT5 attestation: runs one image against a real broker demo account.

Every case uses a real container and real orders. It refuses to trade unless the
broker reports a demo account. Credentials come from an env file with MT5_LOGIN,
MT5_PASSWORD and MT5_SERVER, and never reach the record.

    attestation/run.py --image mt5-gateway:test --variant headless --env-file .env

A full pass writes attestation/records/<source fingerprint>-<variant>.json, which
attestation/verify.py requires before a promotion to main.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import (  # noqa: E402
    BOOT_CASES,
    RECOVERY_CASES,
    SECURITY_CASES,
    SESSION_CASES,
    required_cases,
)
from verify import source_fingerprint  # noqa: E402

DEMO_TRADE_MODE = 0
READY_TIMEOUT_S = 300
RECOVERY_TIMEOUT_S = 300
RECONCILE_S = 8
UNCLEAR_RETRY_S = 120
LATE_FILL_POLL_S = 5
OFFSET_WAIT_S = 60
HISTORY_WAIT_S = 60
TERMINAL_DIR = "/config/.wine/drive_c/Program Files/MetaTrader 5"
START_INI = "/config/.wine/drive_c/start.ini"


class Failed(Exception):
    """A failed attestation check."""


def expect(condition: Any, message: str) -> None:
    if not condition:
        raise Failed(message)


def rows(body: Any, *keys: str) -> list[dict[str, Any]]:
    """Unwraps the list from a reply, e.g. {"data": [...]} -> [...]."""
    found = body.get("data", body) if isinstance(body, dict) else body
    for key in keys:
        if isinstance(found, dict):
            found = found.get(key, found)
    return found if isinstance(found, list) else []


def docker(*args: str, check: bool = True) -> str:
    done = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and done.returncode != 0:
        raise Failed(f"docker {args[0]} failed: {done.stderr.strip()[:300]}")
    return done.stdout


class Gateway:
    """One running container and its API."""

    def __init__(
        self,
        args: argparse.Namespace,
        env_file: Path,
        env: dict[str, str] | None = None,
        volume: str | None = None,
        mounts: tuple[str, ...] = (),
    ) -> None:
        self.args = args
        self.env_file = env_file
        self.extra_env = env or {}
        self.mounts = mounts
        self.name = f"mt5-attest-{uuid.uuid4().hex[:8]}"
        self.volume = volume or self.name
        self.owns_volume = volume is None
        self.api_key = self.extra_env.get("API_KEY", "")
        self.base = f"http://127.0.0.1:{args.port}"

    def __enter__(self) -> Gateway:
        command = ["run", "-d", "--name", self.name, "--env-file", str(self.env_file)]
        command += [
            "-p",
            f"127.0.0.1:{self.args.port}:5001",
            "-v",
            f"{self.volume}:/config",
        ]
        for key, value in self.extra_env.items():
            command += ["-e", f"{key}={value}"]
        for mount in self.mounts:
            command += ["-v", mount]
        docker(*command, self.args.image)
        return self

    def __exit__(self, *_: object) -> None:
        docker("rm", "-f", self.name, check=False)
        if self.owns_volume:
            docker("volume", "rm", self.volume, check=False)

    def exec(self, *command: str, check: bool = False) -> str:
        return docker("exec", self.name, *command, check=check)

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        sent = {"Content-Type": "application/json", **(headers or {})}
        if self.api_key and "Authorization" not in sent:
            sent["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(  # noqa: S310
            self.base + path, data=data, headers=sent, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                raw = response.read()
                return response.status, _parse(raw), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, _parse(error.read()), dict(error.headers)
        except (OSError, ValueError) as error:
            return 0, str(error), {}

    def get(self, path: str) -> tuple[int, Any]:
        status, body, _ = self.call("GET", path)
        return status, body

    def post(self, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        status, reply, _ = self.call("POST", path, body)
        return status, reply

    def wait_ready(self, timeout: int = READY_TIMEOUT_S) -> float:
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            if self.get("/health/ready")[0] == 200:
                return time.monotonic() - started
            time.sleep(2)
        raise Failed(f"not ready after {timeout}s")

    def account(self) -> dict[str, Any]:
        status, body = self.get("/account")
        expect(status == 200, f"/account returned {status}: {body}")
        return body.get("data", body)

    def wait_session(self, login: str, timeout: int = RECOVERY_TIMEOUT_S) -> float:
        """Reconnects happen on API calls, as for a real client, so this polls /account."""
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            status, body = self.get("/account")
            account = body.get("data", body) if isinstance(body, dict) else {}
            if status == 200 and str(account.get("login")) == login:
                return time.monotonic() - started
            time.sleep(3)
        raise Failed(f"session for the configured login not back after {timeout}s")

    def logs(self) -> str:
        done = subprocess.run(
            ["docker", "logs", self.name], capture_output=True, text=True
        )
        return done.stdout + done.stderr


def _parse(raw: bytes) -> Any:
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return raw.decode(errors="replace")[:300]


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


class Run:
    """State shared by the cases of one attestation."""

    def __init__(self, args: argparse.Namespace, secrets: dict[str, str]) -> None:
        self.args = args
        self.login = secrets["MT5_LOGIN"]
        self.password = secrets["MT5_PASSWORD"]
        self.server = secrets["MT5_SERVER"]
        self.symbol = args.symbol
        self.lots = args.lots
        self.work = Path(tempfile.mkdtemp(prefix="mt5-attest-", dir="/dev/shm"))
        self.work.chmod(0o700)
        self.env_file = self.work / "minimal.env"
        self.env_file.write_text(
            f"MT5_LOGIN={self.login}\nMT5_PASSWORD={self.password}\nMT5_SERVER={self.server}\n"
        )
        self.env_file.chmod(0o600)
        self.empty = self.work / "empty"
        self.empty.touch()
        self.empty_table = self.work / "empty.json"
        self.empty_table.write_text("{}")
        self.unclear = {"order_executed": 0, "order_not_executed": 0}
        self.unclear |= {"close_executed": 0, "close_not_executed": 0}
        self.unclear["late_fills"] = 0
        self.issued: set[int] = set()
        self.results: dict[str, dict[str, Any]] = {}

    def gateway(self, **kwargs: Any) -> Gateway:
        return Gateway(self.args, self.env_file, **kwargs)

    def no_servers_dat(self) -> tuple[str, ...]:
        return (f"{self.empty}:/defaults/servers.dat:ro",)

    def magic(self) -> int:
        magic = 700000 + uuid.uuid4().int % 99999
        self.issued.add(magic)
        return magic

    def positions(self, gw: Gateway, magic: int) -> list[dict[str, Any]]:
        status, body = gw.get(f"/get_positions?magic={magic}")
        expect(status in (200, 404), f"/get_positions returned {status}: {body}")
        return [p for p in rows(body, "positions") if p.get("magic") == magic]

    def pending(self, gw: Gateway, magic: int) -> list[dict[str, Any]]:
        status, body = gw.get("/orders")
        expect(status == 200, f"/orders returned {status}: {body}")
        return [o for o in rows(body, "orders") if o.get("magic") == magic]

    def tick(self, gw: Gateway) -> dict[str, Any]:
        status, body = gw.get(f"/symbol_info_tick/{self.symbol}")
        expect(status == 200, f"tick returned {status}: {body}")
        return body.get("data", body)

    def order(
        self,
        gw: Gateway,
        magic: int,
        side: str = "BUY",
        lots: float | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Places an order and returns its one position, reconciling any unclear reply.

        10031 and timeouts can execute at the broker, so an unclear reply is settled from
        the broker's positions before a retry. A retry can then never open a second one.
        """
        body = {
            "symbol": self.symbol,
            "volume": lots or self.lots,
            "type": side,
            "magic": magic,
            "comment": "attestation",
            **extra,
        }
        deadline = time.monotonic() + UNCLEAR_RETRY_S
        while True:
            status, reply = gw.post(
                "/order", {**body, "client_order_id": uuid.uuid4().hex}
            )
            if status == 200:
                break
            if not _unclear(reply):
                raise Failed(f"/order returned {status}: {reply}")
            if _settle(lambda: self.positions(gw, magic)):
                self.unclear["order_executed"] += 1
                break
            self.unclear["order_not_executed"] += 1
            expect(time.monotonic() < deadline, f"/order stayed unclear: {reply}")
        found = self._wait_positions(gw, magic, 1)
        return found[0]

    def _wait_positions(
        self, gw: Gateway, magic: int, count: int
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for _ in range(10):
            found = self.positions(gw, magic)
            if len(found) == count:
                return found
            time.sleep(1)
        raise Failed(
            f"expected {count} positions for magic {magic}, broker has {len(found)}"
        )

    def close(self, gw: Gateway, magic: int, ticket: int) -> None:
        gone = lambda: not any(p["ticket"] == ticket for p in self.positions(gw, magic))  # noqa: E731
        deadline = time.monotonic() + UNCLEAR_RETRY_S
        while True:
            status, reply = gw.post("/close_position", {"position": {"ticket": ticket}})
            if status == 200:
                expect(
                    _settle(gone),
                    f"position {ticket} still open after a successful close",
                )
                return
            if not _unclear(reply):
                raise Failed(f"/close_position returned {status}: {reply}")
            if _settle(gone):
                self.unclear["close_executed"] += 1
                return
            self.unclear["close_not_executed"] += 1
            expect(time.monotonic() < deadline, f"close stayed unclear: {reply}")

    def flatten(self, gw: Gateway, magic: int) -> None:
        """Always runs after a trading case, whatever it did."""
        for _ in range(8):
            for order in self.pending(gw, magic):
                gw.call("DELETE", f"/orders/{order['ticket']}")
            positions = self.positions(gw, magic)
            for position in positions:
                gw.post("/close_position", {"position": {"ticket": position["ticket"]}})
            time.sleep(2)
            if not self.positions(gw, magic) and not self.pending(gw, magic):
                return
        print(f"WARNING: magic {magic} still has open demo exposure", flush=True)

    def round_trip(self, gw: Gateway) -> None:
        magic = self.magic()
        try:
            position = self.order(gw, magic)
            expect(float(position["volume"]) == self.lots, f"wrong volume: {position}")
            self.close(gw, magic, position["ticket"])
        finally:
            self.flatten(gw, magic)


def _unclear(reply: Any) -> bool:
    return isinstance(reply, dict) and reply.get("error_type") in (
        "retryable",
        "unknown_outcome",
    )


def _settle(done: Callable[[], Any]) -> bool:
    deadline = time.monotonic() + RECONCILE_S
    while time.monotonic() < deadline:
        if done():
            return True
        time.sleep(1)
    return bool(done())


# ---- boot and login ----


def _login_and_trade(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    detail["ready_seconds"] = round(gw.wait_ready())
    account = gw.account()
    expect(str(account.get("login")) == run.login, "logged in to the wrong account")
    expect(
        account.get("trade_mode") == DEMO_TRADE_MODE,
        "refusing to trade: not a demo account",
    )
    expect(
        account.get("trade_allowed") and account.get("trade_expert"),
        "algo trading is off",
    )
    run.round_trip(gw)


def boot_fresh_three_vars_no_servers_dat(run: Run, detail: dict[str, Any]) -> None:
    """The promise: an empty volume, no broker file, only server, user and password."""
    times = []
    for _ in range(run.args.boots):
        with run.gateway(mounts=run.no_servers_dat()) as gw:
            boot: dict[str, Any] = {}
            _login_and_trade(run, gw, boot)
            times.append(boot["ready_seconds"])
        time.sleep(20)
    detail["boots"], detail["ready_seconds"] = len(times), times


def boot_resolver_service_only(run: Run, detail: dict[str, Any]) -> None:
    """A broker missing from the baked table: the address must come from the resolver service."""
    mounts = (*run.no_servers_dat(), f"{run.empty_table}:/app/broker_servers.json:ro")
    with run.gateway(mounts=mounts) as gw:
        _login_and_trade(run, gw, detail)


def boot_table_only_no_resolver_service(run: Run, detail: dict[str, Any]) -> None:
    """The resolver service is down: the baked table alone must log in."""
    env = {"MT5_RESOLVER_URL": "http://127.0.0.1:9"}
    with run.gateway(env=env, mounts=run.no_servers_dat()) as gw:
        _login_and_trade(run, gw, detail)


def boot_restart_soon_after_login(run: Run, detail: dict[str, Any]) -> None:
    """A fast restart once let the API launch a terminal with no login config first."""
    with run.gateway() as gw:
        gw.wait_ready()
        times = []
        for _ in range(5):
            time.sleep(20)
            docker("restart", "-t", "20", gw.name)
            times.append(round(gw.wait_ready(120)))
        detail["ready_seconds"] = times
        run.round_trip(gw)


def boot_with_baked_servers_dat(run: Run, detail: dict[str, Any]) -> None:
    with run.gateway() as gw:
        _login_and_trade(run, gw, detail)


def boot_name_only_login(run: Run, detail: dict[str, Any]) -> None:
    with run.gateway(env={"MT5_AUTORESOLVE": "0"}) as gw:
        _login_and_trade(run, gw, detail)


def boot_network_cut_during_login(run: Run, detail: dict[str, Any]) -> None:
    """Every login attempt fails, then the network returns: trading must work."""
    short = {"MT5_LOGIN_FIRST_TRIES": "1", "MT5_LOGIN_TRIES": "1"}
    with run.gateway(env=short) as gw:
        docker("network", "disconnect", "bridge", gw.name)
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            if "No candidate authorized" in gw.exec("cat", "/var/log/mt5_setup.log"):
                break
            time.sleep(5)
        else:
            raise Failed("login loop did not finish while the network was cut")
        docker("network", "connect", "bridge", gw.name)
        detail["session_seconds"] = round(gw.wait_session(run.login))
        time.sleep(10)
        run.round_trip(gw)


def boot_algo_trading_off(run: Run, detail: dict[str, Any]) -> None:
    with run.gateway(env={"MT5_ENABLE_ALGO_TRADING": "0"}) as gw:
        gw.wait_ready()
        magic = run.magic()
        try:
            status, reply = gw.post(
                "/order",
                {
                    "symbol": run.symbol,
                    "volume": run.lots,
                    "type": "BUY",
                    "magic": magic,
                },
            )
            time.sleep(3)
            expect(
                not run.positions(gw, magic), "an order opened with algo trading off"
            )
            detail["reply"] = status
            expect(status != 200, f"order accepted with algo trading off: {reply}")
        finally:
            run.flatten(gw, magic)


def boot_wrong_password_never_logs_in(run: Run, detail: dict[str, Any]) -> None:
    file = run.work / "wrong.env"
    file.write_text(
        f"MT5_LOGIN={run.login}\nMT5_PASSWORD=wrong-{uuid.uuid4().hex}\nMT5_SERVER={run.server}\n"
    )
    short = {"MT5_LOGIN_FIRST_TRIES": "6", "MT5_LOGIN_TRIES": "2"}
    with Gateway(run.args, file, env=short) as gw:
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            expect(gw.get("/health/ready")[0] != 200, "ready with a wrong password")
            time.sleep(5)
        status, _ = gw.post(
            "/order",
            {
                "symbol": run.symbol,
                "volume": run.lots,
                "type": "BUY",
                "magic": run.magic(),
            },
        )
        expect(status != 200, "an order was accepted with a wrong password")
        detail["order_status"] = status


# ---- API on one logged-in session ----


def api_every_read_route(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    start = (now - dt.timedelta(hours=3)).isoformat(timespec="seconds")
    end = now.isoformat(timespec="seconds")
    symbol = run.symbol
    range_query = urllib.parse.urlencode({"from_date": start, "to_date": end})
    for path in (
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/reconcile",
        "/account",
        "/last_error",
        "/last_error_str",
        "/symbols",
        f"/symbols?search={symbol}",
        f"/symbol_info/{symbol}",
        f"/symbol_info_tick/{symbol}",
        f"/fetch_data_pos?symbol={symbol}&timeframe=M1&num_bars=50",
        f"/fetch_data_range?symbol={symbol}&timeframe=M1&start={start}&end={end}",
        f"/copy_ticks_range?symbol={symbol}&{range_query}",
        "/get_positions",
        "/positions_total",
        "/orders",
        f"/history_deals_range?{range_query}",
    ):
        status, body = gw.get(path)
        # A new session's terminal downloads bars in the background, and answers 404 until then.
        deadline = time.monotonic() + HISTORY_WAIT_S
        while status == 404 and "/fetch_data" in path and time.monotonic() < deadline:
            detail["history_waits"] = detail.get("history_waits", 0) + 1
            time.sleep(2)
            status, body = gw.get(path)
        expect(status == 200, f"GET {path} returned {status}: {str(body)[:200]}")
    tick = run.tick(gw)
    expect(float(tick["ask"]) >= float(tick["bid"]) > 0, f"bad tick: {tick}")
    bars = gw.get(f"/fetch_data_pos?symbol={symbol}&timeframe=M1&num_bars=50")[1]
    detail["bars"] = len(rows(bars, "bars"))
    expect(detail["bars"] == 50, f"expected 50 bars, got {detail['bars']}")


def api_calculators_and_order_check(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    ask = float(run.tick(gw)["ask"])
    order = {"symbol": run.symbol, "volume": run.lots, "type": "BUY"}
    status, body = gw.post("/order_check", order)
    expect(status == 200, f"/order_check returned {status}: {body}")
    status, body = gw.post("/order_calc_margin", {**order, "price": ask})
    expect(status == 200, f"/order_calc_margin returned {status}: {body}")
    status, body = gw.post(
        "/order_calc_profit", {**order, "price_open": ask, "price_close": ask + 100}
    )
    expect(status == 200, f"/order_calc_profit returned {status}: {body}")
    expect(
        float(body.get("data", body).get("profit", 0)) > 0,
        f"no profit on a gain: {body}",
    )
    detail["checked"] = 3


def _pip_distance(run: Run, gw: Gateway) -> float:
    """A distance safely outside the symbol's stop level."""
    status, body = gw.get(f"/symbol_info/{run.symbol}")
    expect(status == 200, f"/symbol_info returned {status}: {body}")
    info = body.get("data", body)
    return max(
        float(info["trade_stops_level"]) * float(info["point"]) * 3,
        float(info["ask"]) * 0.02,
    )


def api_market_buy_and_sell(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    for side, kind in (("BUY", 0), ("SELL", 1)):
        magic = run.magic()
        try:
            position = run.order(gw, magic, side)
            expect(
                position["type"] == kind, f"{side} opened as type {position['type']}"
            )
            run.close(gw, magic, position["ticket"])
        finally:
            run.flatten(gw, magic)
    detail["sides"] = 2


def api_sl_tp_set_and_modified(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    distance = _pip_distance(run, gw)
    ask = float(run.tick(gw)["ask"])
    sl, tp = round(ask - distance, 2), round(ask + distance, 2)
    magic = run.magic()
    try:
        position = run.order(gw, magic, sl=sl, tp=tp)
        expect(
            abs(position["sl"] - sl) < 1 and abs(position["tp"] - tp) < 1,
            f"SL/TP: {position}",
        )
        new_sl = round(sl - distance / 2, 2)
        status, reply = gw.post(
            "/modify_sl_tp", {"position": position["ticket"], "sl": new_sl}
        )
        expect(status == 200, f"/modify_sl_tp returned {status}: {reply}")
        time.sleep(1)
        after = run.positions(gw, magic)[0]
        expect(abs(after["sl"] - new_sl) < 1, f"SL not changed: {after}")
        expect(
            abs(after["tp"] - position["tp"]) < 0.01, f"TP was not preserved: {after}"
        )
        detail["tp_preserved"] = True
    finally:
        run.flatten(gw, magic)


def api_partial_close(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    magic = run.magic()
    try:
        position = run.order(gw, magic, lots=run.lots * 2)
        status, reply = gw.post(
            "/position_close_partial",
            {"ticket": position["ticket"], "volume": run.lots},
        )
        expect(status == 200, f"/position_close_partial returned {status}: {reply}")
        time.sleep(1)
        remaining = run.positions(gw, magic)
        expect(len(remaining) == 1, f"partial close left {remaining}")
        expect(
            abs(float(remaining[0]["volume"]) - run.lots) < 1e-9, f"volume: {remaining}"
        )
        detail["remaining"] = remaining[0]["volume"]
    finally:
        run.flatten(gw, magic)


def api_close_all_only_touches_its_magic(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    mine, other = run.magic(), run.magic()
    try:
        run.order(gw, mine)
        run.order(gw, other)
        status, reply = gw.post("/close_all_positions", {"magic": mine})
        expect(status == 200, f"/close_all_positions returned {status}: {reply}")
        expect(_settle(lambda: not run.positions(gw, mine)), "own position still open")
        expect(run.positions(gw, other), "close_all closed another magic's position")
        detail["kept_other_magic"] = True
    finally:
        run.flatten(gw, mine)
        run.flatten(gw, other)


def _place_when_offset_known(
    gw: Gateway, body: dict[str, Any], detail: dict[str, Any]
) -> tuple[int, Any]:
    """A GTD order is refused, placing nothing, until a quote moves and proves the offset."""
    deadline = time.monotonic() + OFFSET_WAIT_S
    while True:
        status, reply = gw.post("/order", body)
        waiting = status == 400 and "broker UTC offset unknown" in str(reply)
        if not waiting or time.monotonic() >= deadline:
            return status, reply
        detail["offset_refusals"] = detail.get("offset_refusals", 0) + 1
        time.sleep(2)


def api_pending_lifecycle(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    """Limit and stop orders, GTD expiry, modification and cancel, from broker truth."""
    distance = _pip_distance(run, gw)
    tick = run.tick(gw)
    ask, bid = float(tick["ask"]), float(tick["bid"])
    expiry = int(time.time()) + 3600
    plans = (
        ("BUY_LIMIT", round(bid - distance, 2), None),
        ("SELL_LIMIT", round(ask + distance, 2), None),
        ("BUY_STOP", round(ask + distance, 2), None),
        ("SELL_STOP", round(bid - distance, 2), expiry),
    )
    for kind, price, expiration in plans:
        magic = run.magic()
        try:
            body = {
                "symbol": run.symbol,
                "volume": run.lots,
                "type": kind,
                "price": price,
                "magic": magic,
                "comment": "attestation",
            }
            if expiration:
                body["expiration"] = expiration
            status, reply = _place_when_offset_known(gw, body, detail)
            expect(status == 200, f"{kind} returned {status}: {reply}")
            orders = run.pending(gw, magic)
            expect(len(orders) == 1, f"{kind}: broker has {orders}")
            ticket = orders[0]["ticket"]
            new_price = round(
                price + (-1 if "LIMIT" in kind and "BUY" in kind else 1) * 10, 2
            )
            status, reply, _ = gw.call("PUT", f"/orders/{ticket}", {"price": new_price})
            expect(status == 200, f"PUT {kind} returned {status}: {reply}")
            time.sleep(1)
            moved = run.pending(gw, magic)[0]
            expect(
                abs(float(moved["price_open"]) - new_price) < 1, f"not moved: {moved}"
            )
            if expiration:
                expect(moved.get("time_expiration"), f"expiry lost by modify: {moved}")
            status, reply, _ = gw.call("DELETE", f"/orders/{ticket}")
            expect(status == 200, f"DELETE {kind} returned {status}: {reply}")
            expect(
                _settle(lambda m=magic: not run.pending(gw, m)), f"{kind} not cancelled"
            )
        finally:
            run.flatten(gw, magic)
    detail["kinds"] = len(plans)


def api_idempotency_replays_and_refuses(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    magic = run.magic()
    key = uuid.uuid4().hex
    body = {"symbol": run.symbol, "volume": run.lots, "type": "BUY", "magic": magic}
    headers = {"Idempotency-Key": key}
    try:
        first = gw.call("POST", "/order", body, headers)
        second = gw.call("POST", "/order", body, headers)
        expect(
            first[0] == second[0], f"replay status differs: {first[0]} then {second[0]}"
        )
        expect(
            second[2].get("Idempotent-Replayed") == "true",
            "second reply is not a replay",
        )
        time.sleep(2)
        count = len(run.positions(gw, magic))
        expect(count <= 1, f"one key opened {count} positions")
        changed = gw.call("POST", "/order", {**body, "volume": run.lots * 2}, headers)
        expect(changed[0] == 409, f"reused key with new params returned {changed[0]}")
        detail["positions"] = count
    finally:
        run.flatten(gw, magic)


def api_invalid_orders_open_nothing(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    magic = run.magic()
    base = {"symbol": run.symbol, "volume": run.lots, "type": "BUY", "magic": magic}
    bad: list[dict[str, Any]] = [
        {**base, "volume": 0},
        {**base, "volume": -0.01},
        {**base, "volume": 1e9},
        {**base, "volume": "NaN"},
        {**base, "volume": "Infinity"},
        {**base, "symbol": "NOPE_NOT_A_SYMBOL"},
        {**base, "type": "SIDEWAYS"},
        {**base, "sl": float(run.tick(gw)["ask"]) * 2},
        {"symbol": run.symbol},
    ]
    try:
        # Above the minimum but off the lot step rounds down, and never up.
        position = run.order(gw, magic, lots=run.lots + 0.0009)
        expect(
            abs(float(position["volume"]) - run.lots) < 1e-9, f"rounded to {position}"
        )
        run.close(gw, magic, position["ticket"])
        for body in bad:
            status, reply = gw.post("/order", body)
            expect(status in (400, 422), f"{body} returned {status}: {reply}")
            expect(
                isinstance(reply, dict) and reply.get("ok") is False,
                f"no error body: {reply}",
            )
        expect(not run.positions(gw, magic), "an invalid order opened a position")
        detail["rejected"] = len(bad)
    finally:
        run.flatten(gw, magic)


def api_closing_a_missing_position_fails_cleanly(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    status, reply = gw.post("/close_position", {"position": {"ticket": 1}})
    expect(status == 400, f"close of a missing position returned {status}: {reply}")
    status, reply, _ = gw.call("DELETE", "/orders/1")
    expect(
        status in (400, 404), f"cancel of a missing order returned {status}: {reply}"
    )
    status, reply = gw.post("/modify_sl_tp", {"position": 1, "sl": 1.0})
    expect(
        status in (400, 404), f"modify of a missing position returned {status}: {reply}"
    )
    detail["clean"] = 3


def api_concurrent_orders_each_open_one(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    magics = [run.magic() for _ in range(6)]
    try:
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            list(pool.map(lambda m: run.order(gw, m), magics))
        time.sleep(2)
        counts = [len(run.positions(gw, m)) for m in magics]
        expect(counts == [1] * 6, f"positions per concurrent order: {counts}")
        detail["orders"] = 6
    finally:
        for magic in magics:
            run.flatten(gw, magic)


def api_concurrent_reads_all_answer(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    paths = [
        "/account",
        f"/symbol_info_tick/{run.symbol}",
        "/get_positions",
        "/orders",
    ] * 10
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        statuses = list(pool.map(lambda p: gw.get(p)[0], paths))
    expect(set(statuses) == {200}, f"statuses under load: {sorted(set(statuses))}")
    detail["reads"] = len(statuses)


def api_history_finds_the_trade(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    magic = run.magic()
    started = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(
        minutes=5
    )
    position = run.order(gw, magic)
    run.close(gw, magic, position["ticket"])
    time.sleep(3)
    query = urllib.parse.urlencode(
        {
            "from_date": started.isoformat(timespec="seconds"),
            "to_date": (started + dt.timedelta(hours=1)).isoformat(timespec="seconds"),
            "magic": magic,
        }
    )
    status, body = gw.get(f"/history_deals_range?{query}")
    expect(status == 200, f"/history_deals_range returned {status}: {body}")
    deals = rows(body, "deals")
    entries = sorted(deal.get("entry") for deal in deals)
    expect(entries == [0, 1], f"expected one open and one close deal, got {entries}")
    ticket = position["ticket"]
    for path in (
        f"/history_deals_get?{query}",
        f"/get_deal_from_ticket?ticket={ticket}",
        f"/get_order_from_ticket?ticket={ticket}",
        f"/history_orders_get?ticket={ticket}",
    ):
        status, reply = gw.get(path)
        expect(status == 200, f"GET {path} returned {status}: {str(reply)[:200]}")
    detail["deals"] = len(deals)


def api_fill_reply_reports_the_real_price(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    """The synchronous fill path; the async one is unit-tested, as demo fills synchronously."""
    magic = run.magic()
    try:
        ask = float(run.tick(gw)["ask"])
        body = {"symbol": run.symbol, "volume": run.lots, "type": "BUY", "magic": magic}
        status, reply = gw.post("/order", {**body, "client_order_id": uuid.uuid4().hex})
        if status != 200:
            expect(_unclear(reply), f"/order returned {status}: {reply}")
            detail["unclear"] = True
            return
        result = reply.get("result", {})
        expect(float(result.get("price", 0)) > 0, f"no fill price: {reply}")
        expect(
            abs(float(result["price"]) - ask) < ask * 0.01,
            f"fill far from market: {reply}",
        )
        detail["fill_price_source"] = reply.get("fill_price_source")
    finally:
        run.flatten(gw, magic)


# ---- security ----


def security_api_key(run: Run, detail: dict[str, Any]) -> None:
    key = uuid.uuid4().hex
    with run.gateway(env={"API_KEY": key}) as gw:
        gw.wait_ready()
        magic = run.magic()
        wrong = {"Authorization": "Bearer wrong"}
        body = {"symbol": run.symbol, "volume": run.lots, "type": "BUY", "magic": magic}
        none_status = gw.call("GET", "/account", headers={"Authorization": ""})[0]
        wrong_status = gw.call("POST", "/order", body, wrong)[0]
        expect(none_status == 401, f"no key returned {none_status}")
        expect(wrong_status == 401, f"wrong key on /order returned {wrong_status}")
        time.sleep(2)
        expect(not run.positions(gw, magic), "an unauthorized order opened a position")
        run.round_trip(gw)
        detail["rejected"] = 2


def security_kill_switch(run: Run, detail: dict[str, Any]) -> None:
    with run.gateway() as gw:
        gw.wait_ready()
        magic = run.magic()
        try:
            position = run.order(gw, magic)
            expect(gw.post("/kill", {})[0] == 200, "could not engage the kill switch")
            other = run.magic()
            body = {
                "symbol": run.symbol,
                "volume": run.lots,
                "type": "BUY",
                "magic": other,
            }
            status, _ = gw.post("/order", body)
            expect(status == 423, f"/order under the kill switch returned {status}")
            expect(
                gw.get("/health/ready")[0] == 200,
                "kill switch made the gateway unready",
            )
            expect(gw.get("/account")[0] == 200, "kill switch blocked reads")
            expect(
                not run.positions(gw, other), "an order opened under the kill switch"
            )
            detail["blocked"] = status
        finally:
            gw.post("/kill/release", {})
            run.flatten(gw, magic)
        run.round_trip(gw)
        expect(position["ticket"], "no position")


def security_no_secret_left_behind(run: Run, detail: dict[str, Any]) -> None:
    with run.gateway() as gw:
        gw.wait_ready()
        run.round_trip(gw)
        deadline = time.monotonic() + 120
        probe = ["docker", "exec", gw.name, "test", "-e", START_INI]
        while subprocess.run(probe, capture_output=True).returncode == 0:
            expect(
                time.monotonic() < deadline,
                "start.ini is still on the volume after 120s",
            )
            time.sleep(3)
        expect(
            run.password not in gw.logs(), "the password appears in the container logs"
        )
        search = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                f"P={run.password}",
                gw.name,
                "bash",
                "-c",
                'grep -rlIF -- "$P" /var/log /tmp /config/.wine/drive_c/start.ini '
                f'"{TERMINAL_DIR}/logs" "{TERMINAL_DIR}/Config" 2>/dev/null | head -3',
            ],
            capture_output=True,
            text=True,
        )
        expect(not search.stdout.strip(), "the password is in a file on the volume")
        detail["clean"] = True


# ---- recovery on one session ----


def recovery_restart(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    started = time.monotonic()
    docker("restart", "-t", "20", gw.name)
    gw.wait_ready()
    gw.wait_session(run.login)
    detail["seconds"] = round(time.monotonic() - started)
    run.round_trip(gw)


def recovery_terminal_crash(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    gw.exec("pkill", "-9", "-f", "terminal64.exe")
    time.sleep(5)
    detail["seconds"] = round(gw.wait_session(run.login) + 5)
    time.sleep(5)
    run.round_trip(gw)


def recovery_api_crash(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    """Only the headless image restarts its API; the VNC image needs a container restart."""
    if run.args.variant != "headless":
        detail["skipped"] = "VNC has no API supervisor"
        return
    gw.exec("pkill", "-9", "-f", "waitress")
    time.sleep(5)
    detail["seconds"] = round(gw.wait_session(run.login) + 5)
    time.sleep(5)
    run.round_trip(gw)


def recovery_network_loss(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    magic = run.magic()
    try:
        position = run.order(gw, magic)
        docker("network", "disconnect", "bridge", gw.name)
        time.sleep(45)
        docker("network", "connect", "bridge", gw.name)
        detail["seconds"] = round(gw.wait_session(run.login))
        time.sleep(15)
        tickets = [p["ticket"] for p in run.positions(gw, magic)]
        expect(position["ticket"] in tickets, "position lost across a network cut")
        run.close(gw, magic, position["ticket"])
    finally:
        run.flatten(gw, magic)
    run.round_trip(gw)


def recovery_stop_is_graceful(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    started = time.monotonic()
    docker("stop", "-t", "30", gw.name)
    detail["seconds"] = round(time.monotonic() - started)
    expect(
        detail["seconds"] < 30, "the container ignored SIGTERM until the stop timeout"
    )
    docker("start", gw.name)
    gw.wait_ready()
    gw.wait_session(run.login)


# ---- surface ----


def surface_processes(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    processes = gw.exec("ps", "-eo", "comm")
    desktop = [name for name in ("Xvnc", "nginx", "openbox") if name in processes]
    if run.args.variant == "headless":
        expect(not desktop, f"desktop processes in the headless image: {desktop}")
        expect("Xvfb" in processes, "Xvfb is not running")
    else:
        expect(len(desktop) == 3, f"VNC desktop is incomplete: {desktop}")
        url = "http://localhost:3000/"
        code = gw.exec("curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url)
        expect(code in ("200", "401"), f"VNC web port answered {code}")
        detail["vnc_http"] = code


def surface_terminal_did_not_change(
    run: Run, gw: Gateway, detail: dict[str, Any]
) -> None:
    """A terminal that auto-updates could reach a build that refuses to start."""
    exe = f"{TERMINAL_DIR}/terminal64.exe"
    build = gw.exec("python3", "/scripts/mt5-terminal-build.py", exe).strip()
    baked = gw.exec("grep", "terminal_build", "/opt/wine-template/.mt5-install-info")
    detail["running"], detail["baked"] = build, baked.strip().partition("=")[2]
    expect(
        build == detail["baked"], f"terminal changed from {detail['baked']} to {build}"
    )


def final_account_is_flat(run: Run, gw: Gateway, detail: dict[str, Any]) -> None:
    """Orders answered unclearly can fill long after the reply, so watch before leaving."""
    deadline = time.monotonic() + run.args.late_fill_watch
    late: set[int] = set()
    while True:
        status, body = gw.get("/get_positions")
        expect(status in (200, 404), f"/get_positions returned {status}: {body}")
        positions = rows(body, "positions")
        foreign = [p["ticket"] for p in positions if p.get("magic") not in run.issued]
        expect(not foreign, f"positions this run did not open: {foreign}")
        for position in positions:
            late.add(position["ticket"])
            gw.post("/close_position", {"position": {"ticket": position["ticket"]}})
        if time.monotonic() >= deadline and not positions:
            break
        expect(
            time.monotonic() < deadline + UNCLEAR_RETRY_S,
            f"positions still open after the watch: {positions}",
        )
        time.sleep(LATE_FILL_POLL_S)
    run.unclear["late_fills"] = len(late)
    detail["late_fills"] = sorted(late)


# ---- runner ----

ALL: dict[str, Callable[..., None]] = {
    name: function for name, function in globals().items() if callable(function)
}


def _timed(run: Run, name: str, call: Callable[[dict[str, Any]], None]) -> None:
    if run.args.only and not any(part in name for part in run.args.only):
        return
    detail: dict[str, Any] = {}
    started = time.monotonic()
    try:
        call(detail)
        ok, error = True, ""
    except Failed as failure:
        ok, error = False, str(failure).replace(run.password, "***")[:600]
    run.results[name] = {
        "ok": ok,
        "seconds": round(time.monotonic() - started),
        "detail": detail,
        **({"error": error} if error else {}),
    }
    print(
        f"{'PASS' if ok else 'FAIL'} {name} {detail if ok else error}"[:400], flush=True
    )


def run_all(run: Run) -> None:
    for name in BOOT_CASES:
        _timed(run, name, lambda d, f=ALL[name]: f(run, d))
        time.sleep(10)
    for name in SECURITY_CASES:
        _timed(run, name, lambda d, f=ALL[name]: f(run, d))
        time.sleep(10)
    with run.gateway() as gw:
        gw.wait_ready()
        gw.wait_session(run.login)
        expect(gw.account().get("trade_mode") == DEMO_TRADE_MODE, "not a demo account")
        for name in SESSION_CASES:
            _timed(run, name, lambda d, f=ALL[name]: f(run, gw, d))
        for name in RECOVERY_CASES:
            _timed(run, name, lambda d, f=ALL[name]: f(run, gw, d))
        # Last, after every login and order this run made.
        _timed(
            run,
            "surface_terminal_did_not_change",
            lambda d: surface_terminal_did_not_change(run, gw, d),
        )
        _timed(
            run, "final_account_is_flat", lambda d: final_account_is_flat(run, gw, d)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--variant", choices=["vnc", "headless"], required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--symbol", default="BTCUSDm", help="a symbol that trades now")
    parser.add_argument("--lots", type=float, default=0.01)
    parser.add_argument("--port", type=int, default=15001)
    parser.add_argument(
        "--boots", type=int, default=5, help="repeats of the fresh boot case"
    )
    parser.add_argument(
        "--late-fill-watch",
        type=int,
        default=720,
        help="seconds to watch for late fills at the end",
    )
    parser.add_argument(
        "--only", nargs="*", help="run only cases with these name parts"
    )
    parser.add_argument(
        "--record", action="store_true", help="write the record on a full pass"
    )
    args = parser.parse_args()
    # A timeout or Ctrl-C must still remove containers and the credential file.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    run = Run(args, read_env_file(args.env_file))
    try:
        run_all(run)
    except Failed as failure:
        print(f"FAIL setup: {str(failure).replace(run.password, '***')}", flush=True)
        run.results["setup"] = {"ok": False}
    finally:
        for file in run.work.iterdir():
            file.unlink()
        run.work.rmdir()

    failed = [name for name, result in run.results.items() if not result["ok"]]
    missing = (
        []
        if args.only
        else sorted(set(required_cases(args.variant)) - set(run.results))
    )
    print(json.dumps({"failed": failed, "missing": missing, "unclear": run.unclear}))
    if args.record and not failed and not missing and not args.only:
        root = Path(__file__).resolve().parent
        fingerprint = source_fingerprint(root.parent)
        record = {
            "fingerprint": fingerprint,
            "variant": args.variant,
            "image_id": docker("inspect", "-f", "{{.Id}}", args.image).strip(),
            "server": run.server,
            "attested_at": dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "unclear_replies": run.unclear,
            "cases": run.results,
        }
        path = root / "records" / f"{fingerprint}-{args.variant}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(f"wrote {path}")
    return 1 if failed or missing else 0


if __name__ == "__main__":
    sys.exit(main())
