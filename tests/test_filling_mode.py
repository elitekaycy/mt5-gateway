from types import SimpleNamespace

import lib
import pytest


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (1, lib.mt5.ORDER_FILLING_FOK),
        (2, lib.mt5.ORDER_FILLING_IOC),
        (3, lib.mt5.ORDER_FILLING_IOC),
        (4, lib.mt5.ORDER_FILLING_RETURN),
        (0, lib.mt5.ORDER_FILLING_RETURN),
    ],
)
def test_symbol_filling_mode_matrix(monkeypatch, flags, expected):
    monkeypatch.setattr(
        lib.mt5,
        "symbol_info",
        lambda _: SimpleNamespace(filling_mode=flags),
        raising=False,
    )

    assert lib.get_symbol_filling_mode("EURUSD") == expected


def test_integer_filling_mode_must_be_known():
    assert lib.validate_type_filling(999)[1] == "Invalid integer type_filling"
