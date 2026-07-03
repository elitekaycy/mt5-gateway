"""Pure builders for MT5 trade requests."""

import math
from typing import Any, Mapping


class OrderRequestError(ValueError):
    """Raised when a trade request cannot be built safely."""


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
            raise OrderRequestError(
                f"{field} cannot be set when {clear_field} is true"
            )
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
