from types import SimpleNamespace

import pytest

from order_requests import OrderRequestError, build_sltp_request


@pytest.fixture
def position():
    return SimpleNamespace(ticket=123, symbol="EURUSD", sl=1.08, tp=1.10)


def test_omitted_sl_is_preserved_when_tp_changes(position):
    request = build_sltp_request({"tp": 1.11}, position, action=6)

    assert request["sl"] == 1.08
    assert request["tp"] == 1.11


def test_omitted_tp_is_preserved_when_sl_changes(position):
    request = build_sltp_request({"sl": 1.09}, position, action=6)

    assert request["sl"] == 1.09
    assert request["tp"] == 1.10


def test_protection_requires_explicit_clear(position):
    with pytest.raises(OrderRequestError, match="clear_sl=true"):
        build_sltp_request({"sl": 0}, position, action=6)

    request = build_sltp_request({"clear_sl": True}, position, action=6)
    assert request["sl"] == 0.0
    assert request["tp"] == 1.10


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_protection_must_be_finite_and_positive(position, value):
    with pytest.raises(OrderRequestError):
        build_sltp_request({"sl": value}, position, action=6)
