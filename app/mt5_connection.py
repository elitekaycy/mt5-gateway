import logging
import os
import time
from enum import Enum
from functools import wraps
from threading import Lock, RLock, local
from typing import Any, Callable, Optional

import MetaTrader5 as _mt5

logger = logging.getLogger(__name__)


class SerializedMT5:
    """Serialize access to the process-global MetaTrader5 IPC client."""

    def __init__(self, module: Any):
        self._module = module
        self._lock = RLock()
        self._local = local()
        self._wrappers: dict[str, Callable[..., Any]] = {}

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
                result = function(*args, **kwargs)
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
        self._reconnect_lock = Lock()

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

    def initialize(self) -> bool:
        attempt = 0
        while attempt < self._max_reconnect_attempts:
            attempt += 1

            if attempt > 1:
                self._set_status(
                    ConnectionStatus.RECONNECTING,
                    f"Reconnection attempt {attempt}/{self._max_reconnect_attempts}",
                )

            try:
                if mt5.initialize():
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

    def ensure_connection(self) -> bool:
        if self.is_connected():
            try:
                account_info = mt5.account_info()
                if account_info is not None:
                    return True
                else:
                    logger.warning("MT5 connection lost, account_info returned None")
                    self._set_status(ConnectionStatus.DISCONNECTED, "Connection lost")
            except Exception as e:
                logger.warning(f"MT5 connection check failed: {str(e)}")
                self._set_status(ConnectionStatus.DISCONNECTED, str(e))

        if not self._reconnect_lock.acquire(blocking=False):
            logger.warning("MT5 reconnect already in progress; failing fast")
            return False
        try:
            if self.is_connected():
                return True
            logger.info("Attempting to reconnect to MT5")
            from metrics import metrics
            from reconciliation import reconcile

            metrics.inc("mt5_reconnects_total")
            if not self.initialize():
                metrics.set("mt5_connected", 0)
                return False
            try:
                reconcile()
            except RuntimeError as error:
                self._set_status(ConnectionStatus.DISCONNECTED, str(error))
                metrics.set("mt5_connected", 0)
                return False
            metrics.set("mt5_connected", 1)
            return True
        finally:
            self._reconnect_lock.release()

    def shutdown(self):
        if self._status != ConnectionStatus.DISCONNECTED:
            try:
                mt5.shutdown()
                logger.info("MT5 connection shut down gracefully")
            except Exception as e:
                logger.error(f"Error during MT5 shutdown: {str(e)}")
            finally:
                self._set_status(ConnectionStatus.DISCONNECTED)
