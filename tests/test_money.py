from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from money import (
    NumericValidationError,
    finite_float,
    normalize_price,
    normalize_volume,
)


@pytest.fixture
def symbol_info():
    return make_symbol_info()


def make_symbol_info():
    return SimpleNamespace(
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        digits=5,
        trade_tick_size=0.00001,
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "-Infinity"])
def test_non_finite_values_are_rejected(value):
    with pytest.raises(NumericValidationError):
        finite_float(value, "value")


def test_volume_is_normalized_to_step(symbol_info):
    assert normalize_volume(0.30000000000000004, symbol_info) == 0.3
    assert Decimal(str(normalize_volume(0.309, symbol_info))) % Decimal("0.01") == 0


def test_price_is_normalized_and_idempotent(symbol_info):
    normalized = normalize_price("1.23456789012", symbol_info)

    assert normalized == 1.23457
    assert normalize_price(normalized, symbol_info) == normalized


@given(st.decimals(min_value="0.01", max_value="100", places=8))
def test_normalized_volume_is_step_aligned_and_idempotent(value):
    symbol_info = make_symbol_info()
    normalized = normalize_volume(value, symbol_info)

    assert Decimal(str(normalized)) % Decimal("0.01") == 0
    assert normalize_volume(normalized, symbol_info) == normalized
