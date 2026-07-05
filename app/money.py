"""Finite parsing and Decimal normalization for broker-bound numbers."""

import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


class NumericValidationError(ValueError):
    """Raised when a broker-bound numeric value is unsafe."""


def finite_decimal(value: Any, field: str) -> Decimal:
    """Parse a finite decimal without inheriting binary-float noise."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise NumericValidationError(f"{field} must be numeric") from error
    if not result.is_finite():
        raise NumericValidationError(f"{field} must be finite")
    return result


def finite_float(value: Any, field: str) -> float:
    """Parse a finite float for an API that requires C doubles."""
    result = float(finite_decimal(value, field))
    if not math.isfinite(result):
        raise NumericValidationError(f"{field} must be finite")
    return result


def normalize_volume(value: Any, symbol_info: Any) -> float:
    """Round an opening volume down to the broker's lot step."""
    volume = finite_decimal(value, "volume")
    minimum = Decimal(str(symbol_info.volume_min))
    maximum = Decimal(str(symbol_info.volume_max))
    step = Decimal(str(symbol_info.volume_step))
    if volume < minimum or volume > maximum:
        raise NumericValidationError(f"volume must be between {minimum} and {maximum}")
    if step <= 0:
        return float(volume)
    normalized = (volume / step).to_integral_value(rounding=ROUND_DOWN) * step
    if normalized < minimum:
        raise NumericValidationError(f"volume must be at least {minimum}")
    return float(normalized)


def normalize_price(value: Any, symbol_info: Any, field: str = "price") -> float:
    """Snap a price to tick size and the symbol's displayed precision."""
    price = finite_decimal(value, field)
    if price <= 0:
        raise NumericValidationError(f"{field} must be positive")
    tick_size = Decimal(str(getattr(symbol_info, "trade_tick_size", 0) or 0))
    if tick_size > 0:
        price = (price / tick_size).to_integral_value(
            rounding=ROUND_HALF_UP
        ) * tick_size
    digits = int(symbol_info.digits)
    quantum = Decimal(1).scaleb(-digits)
    return float(price.quantize(quantum, rounding=ROUND_HALF_UP))
