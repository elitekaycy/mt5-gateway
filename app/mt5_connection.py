import logging
import os
import time
from enum import Enum
from threading import Lock
from typing import Optional

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

# Serialize every mt5.order_send call across the waitress worker pool. The
# MT5 Python DLL is not thread-safe: two concurrent order_send invocations on
# different waitress threads caused the second to return None (observed
# reproducibly on Exness demo SELL-after-BUY straddle legs, zero failures
# after this lock was added).
_ORDER_SEND_LOCK = Lock()
_original_order_send = mt5.order_send

def _locked_order_send(request):
    with _ORDER_SEND_LOCK:
        result = _original_order_send(request)
        if result is None:
            err = mt5.last_error()
            logger.error(f"mt5.order_send returned None - last_error={err}")
        return result

mt5.order_send = _locked_order_send


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class MT5Connection:
    _instance: Optional['MT5Connection'] = None
    _lock = Lock()

    def __init__(self):
        self._status = ConnectionStatus.DISCONNECTED
        self._last_error: Optional[str] = None
        self._max_reconnect_attempts = int(os.getenv('MT5_RECONNECT_ATTEMPTS', '3'))
        self._base_delay = float(os.getenv('MT5_RECONNECT_BASE_DELAY', '1.0'))

    @classmethod
    def get_instance(cls) -> 'MT5Connection':
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
            logger.info(f"MT5 connection state changed", extra={
                "old_status": old_status.value,
                "new_status": new_status.value,
                "error": error
            })

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
                self._set_status(ConnectionStatus.RECONNECTING, f"Reconnection attempt {attempt}/{self._max_reconnect_attempts}")

            try:
                if mt5.initialize():
                    account_info = mt5.account_info()
                    if account_info is not None:
                        logger.info(f"MT5 initialized successfully", extra={
                            "account": account_info.login,
                            "server": account_info.server,
                            "attempt": attempt
                        })
                        self._set_status(ConnectionStatus.CONNECTED)
                        return True

                error_code, error_str = mt5.last_error()
                error_msg = f"MT5 initialization failed: {error_str} (code: {error_code})"
                logger.error(error_msg, extra={"attempt": attempt})
                self._set_status(ConnectionStatus.DISCONNECTED, error_msg)

            except Exception as e:
                error_msg = f"Exception during MT5 initialization: {str(e)}"
                logger.error(error_msg, extra={"attempt": attempt})
                self._set_status(ConnectionStatus.DISCONNECTED, error_msg)

            if attempt < self._max_reconnect_attempts:
                delay = self._base_delay * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay}s", extra={"attempt": attempt, "delay": delay})
                time.sleep(delay)

        final_error = f"Failed to initialize MT5 after {self._max_reconnect_attempts} attempts"
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

        logger.info("Attempting to reconnect to MT5")
        return self.initialize()

    def shutdown(self):
        if self._status != ConnectionStatus.DISCONNECTED:
            try:
                mt5.shutdown()
                logger.info("MT5 connection shut down gracefully")
            except Exception as e:
                logger.error(f"Error during MT5 shutdown: {str(e)}")
            finally:
                self._set_status(ConnectionStatus.DISCONNECTED)
