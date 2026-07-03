import pytest
from pretrade import (
    PreTradeError,
    PreTradeLimits,
    validate_order_intent,
    validate_price_band,
)

LIMITS = PreTradeLimits(
    symbols=frozenset({"EURUSD"}),
    max_volume=2.0,
    max_price_deviation_pct=5.0,
    max_deviation=100,
)


def test_pretrade_rejects_symbol_volume_and_unknown_fields():
    with pytest.raises(PreTradeError, match="not allowed"):
        validate_order_intent({"symbol": "BTCUSD", "volume": 1, "type": "BUY"}, LIMITS)
    with pytest.raises(PreTradeError, match="operator maximum"):
        validate_order_intent({"symbol": "EURUSD", "volume": 3, "type": "BUY"}, LIMITS)
    with pytest.raises(PreTradeError, match="Unknown"):
        validate_order_intent(
            {"symbol": "EURUSD", "volume": 1, "type": "BUY", "oops": 1},
            LIMITS,
        )


def test_pretrade_rejects_fat_finger_price():
    with pytest.raises(PreTradeError, match="market-price band"):
        validate_price_band(1.20, 1.00, LIMITS)


def test_pretrade_accepts_bounded_order():
    validate_order_intent(
        {"symbol": "EURUSD", "volume": 1, "type": "BUY", "magic": 42},
        LIMITS,
    )
