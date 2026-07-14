"""Pure builders for MT5 trade requests."""

import math
from collections.abc import Mapping
from typing import Any, Optional


class OrderRequestError(ValueError):
    """Raised when a trade request cannot be built safely."""


# The native API rejects long comments before producing any retcode:
# mt5.order_check/order_send fail with (-2, 'Invalid "comment" argument')
# at roughly 30 characters, and brokers store at most ~16 anyway (Exness
# keeps a 16-char prefix). Truncation loses nothing the venue would keep —
# client identity travels in client_order_id / Idempotency-Key, never in
# the comment.
MAX_COMMENT_LENGTH = 25


def build_trade_request(
    *,
    action: int,
    symbol: str,
    volume: float,
    order_type: int,
    price: float,
    deviation: int,
    magic: int,
    comment: str,
    type_time: int,
    type_filling: int,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
) -> dict[str, Any]:
    """Build the canonical request shared by order-check and order-send."""
    request = {
        "action": action,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment[:MAX_COMMENT_LENGTH],
        "type_time": type_time,
        "type_filling": type_filling,
    }
    if sl is not None:
        request["sl"] = sl
    if tp is not None:
        request["tp"] = tp
    return request


def build_sltp_request(
    data: Mapping[str, Any], position: Any, action: int
) -> dict[str, Any]:
    """Build an SL/TP request while preserving omitted protection levels."""
    if not any(field in data for field in ("sl", "tp", "clear_sl", "clear_tp")):
        raise OrderRequestError("Provide sl or tp, or explicitly clear one")

    sl = _resolve_protection_level(data, "sl", position.sl)
    tp = _resolve_protection_level(data, "tp", position.tp)

    return {
        "action": action,
        "symbol": position.symbol,
        "position": position.ticket,
        "sl": sl,
        "tp": tp,
    }


def _resolve_protection_level(
    data: Mapping[str, Any], field: str, current_value: float
) -> float:
    clear_field = f"clear_{field}"
    clear = data.get(clear_field, False)
    if not isinstance(clear, bool):
        raise OrderRequestError(f"{clear_field} must be a boolean")

    if clear:
        if field in data and data[field] not in (None, 0, 0.0):
            raise OrderRequestError(f"{field} cannot be set when {clear_field} is true")
        return 0.0

    if field not in data:
        return float(current_value)

    try:
        value = float(data[field])
    except (TypeError, ValueError) as error:
        raise OrderRequestError(f"{field} must be numeric") from error

    if not math.isfinite(value) or value <= 0:
        raise OrderRequestError(
            f"{field} must be finite and positive; use {clear_field}=true to remove it"
        )
    return value
