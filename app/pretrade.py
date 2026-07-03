"""Operator-controlled pre-trade limits."""

import os
from dataclasses import dataclass


class PreTradeError(ValueError):
    pass


ALLOWED_ORDER_FIELDS = {
    "symbol",
    "volume",
    "type",
    "price",
    "sl",
    "tp",
    "deviation",
    "magic",
    "comment",
    "type_filling",
    "expiration",
    "client_order_id",
}


@dataclass(frozen=True)
class PreTradeLimits:
    symbols: frozenset[str]
    max_volume: float
    max_price_deviation_pct: float
    max_deviation: int

    @classmethod
    def from_env(cls):
        return cls(
            symbols=frozenset(
                symbol.strip()
                for symbol in os.getenv("SYMBOL_WHITELIST", "").split(",")
                if symbol.strip()
            ),
            max_volume=float(os.getenv("MAX_ORDER_VOLUME", "100")),
            max_price_deviation_pct=float(os.getenv("MAX_PRICE_DEVIATION_PCT", "20")),
            max_deviation=int(os.getenv("MAX_ORDER_DEVIATION", "1000")),
        )


def validate_order_intent(data, limits=None):
    limits = limits or PreTradeLimits.from_env()
    unknown = set(data) - ALLOWED_ORDER_FIELDS
    if unknown:
        raise PreTradeError(f"Unknown order fields: {', '.join(sorted(unknown))}")
    symbol = data.get("symbol")
    if limits.symbols and symbol not in limits.symbols:
        raise PreTradeError(f"Symbol is not allowed: {symbol}")
    try:
        volume = float(data["volume"])
        deviation = int(data.get("deviation", 20))
        magic = int(data.get("magic", 0))
    except (KeyError, TypeError, ValueError) as error:
        raise PreTradeError("volume, deviation, and magic must be numeric") from error
    if volume > limits.max_volume:
        raise PreTradeError(f"Volume exceeds operator maximum {limits.max_volume}")
    if not 0 <= deviation <= limits.max_deviation:
        raise PreTradeError(f"deviation must be between 0 and {limits.max_deviation}")
    if not 0 <= magic <= 0xFFFFFFFF:
        raise PreTradeError("magic must be an unsigned 32-bit integer")


def validate_price_band(price, market_price, limits=None):
    limits = limits or PreTradeLimits.from_env()
    if market_price <= 0:
        raise PreTradeError("Current market price is unavailable")
    deviation_pct = abs(price - market_price) / market_price * 100
    if deviation_pct > limits.max_price_deviation_pct:
        raise PreTradeError(
            f"Price exceeds {limits.max_price_deviation_pct}% market-price band"
        )
