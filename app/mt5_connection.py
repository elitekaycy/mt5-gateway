import logging
import os
import time
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import Event, Lock, RLock, Thread, local
from typing import Any, Callable, Optional

import MetaTrader5 as _mt5

from autologin import (
    LOGIN_SERVER_FILE,
    SESSION_MARKER,
    read_login_server,
    reconnect_credentials,
    wine_path,
    write_session_marker,
)
from time_utils import (
    derive_from_tick,
    live_tick,
    resolve_offset_seconds,
    tick_time_ms,
)

logger = logging.getLogger(__name__)

# MetaTrader5 last_error codes <= -10000 are internal IPC failures
# (RES_E_INTERNAL_FAIL, _SEND, _RECEIVE, _INIT, _CONNECT, _TIMEOUT): the
# terminal-side connection is gone. Benign None results (unknown symbol, no
# history match) carry higher codes.
MT5_IPC_FAILURE_CODE = -10000


def is_ipc_failure(error: Any) -> bool:
    """Return True when a ``last_error()`` tuple reports an internal IPC failure."""
    return (
        isinstance(error, tuple)
        and len(error) >= 1
        and isinstance(error[0], int)
        and error[0] <= MT5_IPC_FAILURE_CODE
    )


class SerializedMT5:
    """Serialize access to the process-global MetaTrader5 IPC client."""

    def __init__(self, module: Any):
        self._module = module
        self._lock = RLock()
        self._local = local()
        self._wrappers: dict[str, Callable[..., Any]] = {}
        self._connection_failure_callback: Optional[Callable[[Any], None]] = None

    def set_connection_failure_callback(
        self, callback: Optional[Callable[[Any], None]]
    ) -> None:
        """Register a hook invoked with the ``last_error`` of IPC-level failures.

        Invoked inside the serialized boundary when a call returns None with an
        internal/IPC ``last_error`` code, so the callback must not make MT5
        calls itself.
        """
        self._connection_failure_callback = callback

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._module, name)
        if not callable(attribute):
            return attribute

        if name not in self._wrappers:
            self._wrappers[name] = self._wrap(name, attribute)
        return self._wrappers[name]

    def _wrap(self, name: str, function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(function)
        def serialized(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                # MetaTrader5's request functions (order_check, order_send)
                # reject any call made with a kwargs splat -- even an empty
                # one -- returning None with (-2, 'Unnamed arguments not
                # allowed'). Splat kwargs only when there are kwargs.
                result = function(*args, **kwargs) if kwargs else function(*args)
                if (
                    name not in {"last_error", "shutdown"}
                    and result is None
                    and hasattr(self._module, "last_error")
                ):
                    error = self._module.last_error()
                    self._local.last_call_error = error
                    if name == "order_send":
                        logger.error(
                            "mt5.order_send returned None - last_error=%s", error
                        )
                    if (
                        is_ipc_failure(error)
                        and self._connection_failure_callback is not None
                    ):
                        self._connection_failure_callback(error)
                return result

        return serialized

    def last_order_error(self) -> Any:
        """Return the error captured atomically with this thread's order_send."""
        return self.last_call_error()

    def last_call_error(self) -> Any:
        """Return the error captured atomically with the last failed MT5 call."""
        return getattr(self._local, "last_call_error", None)

    def call_atomic(self, operation: Callable[[Any], Any]) -> Any:
        """Run a multi-call MT5 operation without allowing interleaving."""
        with self._lock:
            return operation(self._module)


mt5 = SerializedMT5(_mt5)


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class MT5Connection:
    _instance: Optional["MT5Connection"] = None
    _lock = Lock()

    def __init__(self):
        self._status = ConnectionStatus.DISCONNECTED
        self._last_error: Optional[str] = None
        self._max_reconnect_attempts = int(os.getenv("MT5_RECONNECT_ATTEMPTS", "3"))
        self._base_delay = float(os.getenv("MT5_RECONNECT_BASE_DELAY", "1.0"))
        self._verify_ttl_seconds = float(
            os.getenv("MT5_CONNECTION_VERIFY_TTL_SECONDS", "30")
        )
        self._last_verified_at = 0.0
        self._verify_lock = Lock()
        self._reconnect_lock = Lock()
        self._cooldown_base = float(os.getenv("MT5_RECONNECT_COOLDOWN_SECONDS", "5"))
        self._cooldown_max = float(
            os.getenv("MT5_RECONNECT_COOLDOWN_MAX_SECONDS", "60")
        )
        self._failed_reconnects = 0
        self._reconnect_not_before = 0.0
        self._offset_refresher: Optional[Thread] = None
        self._offset_refresh_stop = Event()

    @classmethod
    def get_instance(cls) -> "MT5Connection":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _set_status(self, new_status: ConnectionStatus, error: Optional[str] = None):
        old_status = self._status
        self._status = new_status
        self._last_error = error

        if new_status == ConnectionStatus.CONNECTED:
            # A freshly (re)connected and reconciled session counts as verified.
            self._last_verified_at = time.monotonic()

        if old_status != new_status:
            logger.info(
                "MT5 connection state changed",
                extra={
                    "old_status": old_status.value,
                    "new_status": new_status.value,
                    "error": error,
                },
            )

    def is_connected(self) -> bool:
        return self._status == ConnectionStatus.CONNECTED

    def get_status(self) -> ConnectionStatus:
        return self._status

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def initialize(self, credentials: Optional[dict] = None) -> bool:
        """Attach to the terminal, retrying with backoff.

        Args:
            credentials: ``login``/``password``/``server`` passed to
                ``mt5.initialize`` so a terminal it has to launch logs in. The
                boot attach passes none: the boot script's terminal is already
                logging in from its ini, and a second login would race it.
        """
        attempt = 0
        while attempt < self._max_reconnect_attempts:
            attempt += 1

            if attempt > 1:
                self._set_status(
                    ConnectionStatus.RECONNECTING,
                    f"Reconnection attempt {attempt}/{self._max_reconnect_attempts}",
                )

            try:
                attached = (
                    mt5.initialize(**credentials) if credentials else mt5.initialize()
                )
                if attached:
                    account_info = mt5.account_info()
                    if account_info is not None:
                        logger.info(
                            "MT5 initialized successfully",
                            extra={
                                "account": account_info.login,
                                "server": account_info.server,
                                "attempt": attempt,
                            },
                        )
                        self._set_status(ConnectionStatus.CONNECTED)
                        self._mark_session(account_info.login)
                        self._refresh_server_offset()
                        self.start_offset_refresher()
                        return True

                error_code, error_str = mt5.last_error()
                error_msg = (
                    f"MT5 initialization failed: {error_str} (code: {error_code})"
                )
                logger.error(error_msg, extra={"attempt": attempt})
                self._set_status(ConnectionStatus.DISCONNECTED, error_msg)

            except Exception as e:
                error_msg = f"Exception during MT5 initialization: {str(e)}"
                logger.error(error_msg, extra={"attempt": attempt})
                self._set_status(ConnectionStatus.DISCONNECTED, error_msg)

            if attempt < self._max_reconnect_attempts:
                delay = self._base_delay * (2 ** (attempt - 1))
                logger.info(
                    f"Retrying in {delay}s", extra={"attempt": attempt, "delay": delay}
                )
                time.sleep(delay)

        final_error = (
            f"Failed to initialize MT5 after {self._max_reconnect_attempts} attempts"
        )
        logger.error(final_error)
        self._set_status(ConnectionStatus.DISCONNECTED, final_error)
        return False

    @staticmethod
    def _mark_session(login: Any) -> None:
        """Tell the boot login loop the API holds a logged-in session (best effort)."""
        marker = os.getenv("MT5_SESSION_MARKER", SESSION_MARKER)
        try:
            write_session_marker(
                Path(wine_path(marker, os.name == "nt")), str(login), time.time()
            )
        except OSError as error:
            logger.warning("Session marker not written: %s", error)

    @staticmethod
    def _reconnect_credentials() -> dict:
        """Credentials for a reconnect, so a terminal it relaunches logs in."""
        server_file = os.getenv("MT5_LOGIN_SERVER_FILE", LOGIN_SERVER_FILE)
        login_server = read_login_server(Path(wine_path(server_file, os.name == "nt")))
        return reconnect_credentials(os.environ, login_server)

    def _reconnect_cooling_down(self) -> bool:
        """True inside the back-off window that follows a failed reconnect."""
        return time.monotonic() < self._reconnect_not_before

    def _note_reconnect_outcome(self, connected: bool) -> None:
        """Reset the back-off on success; double it (capped) on failure.

        Without it every request that arrives after a failed reconnect starts
        another ``initialize()``, and each one can launch a terminal of its
        own; under a steady client load that is a relaunch storm racing the
        boot login loop for the terminal's single-instance lock.
        """
        if connected:
            self._failed_reconnects = 0
            self._reconnect_not_before = 0.0
            return
        self._failed_reconnects += 1
        delay = min(
            self._cooldown_max,
            self._cooldown_base * (2 ** (self._failed_reconnects - 1)),
        )
        self._reconnect_not_before = time.monotonic() + delay
        logger.warning(
            "MT5 reconnect failed; next attempt in %.0fs",
            delay,
            extra={"failed_reconnects": self._failed_reconnects},
        )

    def _refresh_server_offset(self) -> None:
        """Derive the broker UTC offset from a fresh quote and cache it for GTD math.

        Runs on every (re)connect so it re-derives across DST. Only a live quote may
        derive: this polls ``symbol_info_tick`` up to ``MT5_TIME_DERIVE_ATTEMPTS`` times
        (``MT5_TIME_DERIVE_DELAY`` seconds apart) and uses the freshest symbol whose
        tick advanced since the previous read. A frozen quote -- a symbol just added to
        Market Watch, a closed market, or a feed stalled by a network drop -- repeats
        its last tick and can be stale by close to a whole number of hours, so it never
        derives. The first read is only a baseline. Best-effort: an explicit
        ``MT5_SERVER_UTC_OFFSET_SECONDS`` env is left to win, and if no fresh quote
        arrives (e.g. market closed) the offset stays unresolved so GTD placement
        fails loud rather than guessing UTC. Never propagates -- a derivation
        failure must not fail an otherwise-healthy connection.
        """
        attempts = int(os.getenv("MT5_TIME_DERIVE_ATTEMPTS", "10"))
        delay = float(os.getenv("MT5_TIME_DERIVE_DELAY", "0.5"))
        try:
            candidates = self._offset_reference_symbols()
            derived = None
            used: Optional[str] = None
            previous: dict = {}
            for attempt in range(attempts):
                current = {
                    symbol: tick_time_ms(mt5.symbol_info_tick(symbol))
                    for symbol in candidates
                }
                live = live_tick(previous, current)
                if live is not None:
                    derived = derive_from_tick(live[0], live[1] / 1000)
                    if derived is not None:
                        used = live[0]
                        break
                previous = current
                if attempt < attempts - 1:
                    time.sleep(delay)
            if derived is None:
                logger.warning(
                    "Broker UTC offset not derived: no live quote on %s after %d attempts",
                    ", ".join(candidates[:8]) or "(no symbols)",
                    attempts,
                )
            logger.info(
                "Broker UTC offset %s",
                "resolved" if resolve_offset_seconds() is not None else "not resolved",
                extra={
                    "offset_seconds": resolve_offset_seconds(),
                    "reference_symbol": used,
                    "derived": derived,
                },
            )
        except Exception as error:
            logger.warning("Broker UTC offset derivation skipped: %s", error)

    def _offset_reference_symbols(self) -> list:
        """Symbols whose quotes may derive the server offset, best first.

        An explicit ``MT5_TIME_REFERENCE_SYMBOL`` is tried first. Otherwise every symbol
        visible in Market Watch is a candidate — the account's own naming, whatever the
        broker's suffix or prefix scheme, and 24/7 crypto keeps it working at weekends.
        ``EURUSD`` is only the fallback when Market Watch cannot be listed.
        """
        explicit = os.getenv("MT5_TIME_REFERENCE_SYMBOL", "").strip()
        candidates: list = []
        if explicit:
            mt5.symbol_select(explicit, True)
            candidates.append(explicit)
        listing = getattr(mt5, "symbols_get", None)
        watched = listing() if listing is not None else None
        if watched:
            for info in watched:
                name = getattr(info, "name", None)
                if name and getattr(info, "visible", True) and name not in candidates:
                    candidates.append(name)
        if not candidates:
            mt5.symbol_select("EURUSD", True)
            candidates.append("EURUSD")
        return candidates

    def start_offset_refresher(self) -> None:
        """Re-derive the server offset periodically so a DST switch or a market that was
        closed at boot cannot leave a stale or missing offset for the life of the
        connection. ``MT5_TIME_REFRESH_SECONDS`` sets the period; 0 disables it.
        """
        period = float(os.getenv("MT5_TIME_REFRESH_SECONDS", "600"))
        if period <= 0 or self._offset_refresher is not None:
            return

        def loop() -> None:
            while not self._offset_refresh_stop.wait(period):
                if self.is_connected():
                    self._refresh_server_offset()

        self._offset_refresher = Thread(
            target=loop, name="mt5-offset-refresh", daemon=True
        )
        self._offset_refresher.start()

    def note_connection_failure(self, error: Any) -> None:
        """Mark the connection disconnected after an IPC-level MT5 call failure.

        Called by the ``SerializedMT5`` boundary when a call returns None with
        an internal/IPC ``last_error`` code, so the next request runs the full
        reconnect-and-reconcile path instead of trusting a dead session. Benign
        None results (non-IPC error codes) never reach this hook.
        """
        if self.is_connected():
            self._set_status(ConnectionStatus.DISCONNECTED, f"MT5 IPC failure: {error}")

    def _verification_fresh(self) -> bool:
        """Return True while the last live verification is inside the TTL."""
        return (time.monotonic() - self._last_verified_at) < self._verify_ttl_seconds

    def _verify_live_connection(self) -> bool:
        """Re-verify a connected session with one ``account_info()`` round trip.

        Serialized on ``_verify_lock`` with a double-checked freshness test so
        a burst of concurrent requests pays for a single probe per TTL window.
        A failed probe marks the connection DISCONNECTED.
        """
        with self._verify_lock:
            if not self.is_connected():
                return False
            if self._verification_fresh():
                return True
            try:
                account_info = mt5.account_info()
                if account_info is not None:
                    self._last_verified_at = time.monotonic()
                    return True
                logger.warning("MT5 connection lost, account_info returned None")
                self._set_status(ConnectionStatus.DISCONNECTED, "Connection lost")
            except Exception as e:
                logger.warning(f"MT5 connection check failed: {str(e)}")
                self._set_status(ConnectionStatus.DISCONNECTED, str(e))
            return False

    def ensure_connection(self) -> bool:
        """Return True when the MT5 session is usable, reconnecting if needed.

        Cheap in the steady connected state: while CONNECTED, the cached state
        is trusted and a live ``account_info()`` probe runs at most once per
        ``MT5_CONNECTION_VERIFY_TTL_SECONDS`` window (default 30s; 0 restores
        probing on every call). Disconnects are otherwise detected immediately
        via ``note_connection_failure`` from the serialized IPC boundary.
        """
        if self.is_connected():
            if self._verification_fresh():
                return True
            if self._verify_live_connection():
                return True

        if self._reconnect_cooling_down():
            return False
        if not self._reconnect_lock.acquire(blocking=False):
            logger.warning("MT5 reconnect already in progress; failing fast")
            return False
        try:
            if self.is_connected():
                return True
            if self._reconnect_cooling_down():
                return False
            logger.info("Attempting to reconnect to MT5")
            from metrics import metrics
            from reconciliation import reconcile

            metrics.inc("mt5_reconnects_total")
            if not self.initialize(self._reconnect_credentials()):
                metrics.set("mt5_connected", 0)
                self._note_reconnect_outcome(False)
                return False
            try:
                reconcile()
            except RuntimeError as error:
                self._set_status(ConnectionStatus.DISCONNECTED, str(error))
                metrics.set("mt5_connected", 0)
                self._note_reconnect_outcome(False)
                return False
            metrics.set("mt5_connected", 1)
            self._note_reconnect_outcome(True)
            return True
        finally:
            self._reconnect_lock.release()

    def shutdown(self):
        self._offset_refresh_stop.set()
        if self._status != ConnectionStatus.DISCONNECTED:
            try:
                mt5.shutdown()
                logger.info("MT5 connection shut down gracefully")
            except Exception as e:
                logger.error(f"Error during MT5 shutdown: {str(e)}")
            finally:
                self._set_status(ConnectionStatus.DISCONNECTED)


# IPC-level call failures (terminal dropped) flip the singleton connection to
# DISCONNECTED so the next ensure_connection() runs the full reconnect path.
mt5.set_connection_failure_callback(
    lambda error: MT5Connection.get_instance().note_connection_failure(error)
)
