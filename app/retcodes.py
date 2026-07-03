"""Classification of MetaTrader 5 trade-server return codes."""

from dataclasses import dataclass
from enum import Enum


class RetcodeClass(Enum):
    SUCCESS = "success"
    RETRYABLE = "retryable"
    AMBIGUOUS = "ambiguous"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class RetcodeInfo:
    name: str
    classification: RetcodeClass

    @property
    def is_success(self) -> bool:
        return self.classification is RetcodeClass.SUCCESS

    @property
    def is_retryable(self) -> bool:
        return self.classification is RetcodeClass.RETRYABLE

    @property
    def is_ambiguous(self) -> bool:
        return self.classification is RetcodeClass.AMBIGUOUS


_SUCCESS = {
    10008: "PLACED",
    10009: "DONE",
    10010: "DONE_PARTIAL",
}

_RETRYABLE = {
    10004: "REQUOTE",
    10020: "PRICE_CHANGED",
    10021: "PRICE_OFF",
    10024: "TOO_MANY_REQUESTS",
    10031: "CONNECTION",
}

_AMBIGUOUS = {
    10012: "TIMEOUT",
}

_PERMANENT = {
    10006: "REJECT",
    10007: "CANCEL",
    10011: "ERROR",
    10013: "INVALID",
    10014: "INVALID_VOLUME",
    10015: "INVALID_PRICE",
    10016: "INVALID_STOPS",
    10017: "TRADE_DISABLED",
    10018: "MARKET_CLOSED",
    10019: "NO_MONEY",
    10022: "INVALID_EXPIRATION",
    10023: "ORDER_CHANGED",
    10025: "NO_CHANGES",
    10026: "SERVER_DISABLES_AT",
    10027: "CLIENT_DISABLES_AT",
    10028: "LOCKED",
    10029: "FROZEN",
    10030: "INVALID_FILL",
    10032: "ONLY_REAL",
    10033: "LIMIT_ORDERS",
    10034: "LIMIT_VOLUME",
    10035: "INVALID_ORDER",
    10036: "POSITION_CLOSED",
    10038: "INVALID_CLOSE_VOLUME",
    10039: "CLOSE_ORDER_EXIST",
}


def classify_retcode(retcode: int) -> RetcodeInfo:
    """Return the retry/success semantics for an MT5 trade retcode."""
    if retcode in _SUCCESS:
        return RetcodeInfo(_SUCCESS[retcode], RetcodeClass.SUCCESS)
    if retcode in _RETRYABLE:
        return RetcodeInfo(_RETRYABLE[retcode], RetcodeClass.RETRYABLE)
    if retcode in _AMBIGUOUS:
        return RetcodeInfo(_AMBIGUOUS[retcode], RetcodeClass.AMBIGUOUS)
    if retcode in _PERMANENT:
        return RetcodeInfo(_PERMANENT[retcode], RetcodeClass.PERMANENT)
    return RetcodeInfo(f"UNKNOWN_{retcode}", RetcodeClass.AMBIGUOUS)


def success_state(retcode: int) -> str:
    """Return a stable API state for a successful trade result."""
    return {
        10008: "placed",
        10009: "executed",
        10010: "partially_executed",
    }.get(retcode, "unknown")
