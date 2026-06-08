from order_time import apply_expiration

ORDER_TIME_GTC = 0
ORDER_TIME_SPECIFIED = 2


def test_absent_expiration_leaves_gtc_untouched():
    req = {"action": 5, "type_time": ORDER_TIME_GTC, "type_filling": 1}
    apply_expiration(req, {})
    assert req["type_time"] == ORDER_TIME_GTC
    assert "expiration" not in req


def test_none_expiration_is_a_noop():
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": None})
    assert req["type_time"] == ORDER_TIME_GTC
    assert "expiration" not in req


def test_expiration_switches_to_specified():
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": 1780917192})
    assert req["type_time"] == ORDER_TIME_SPECIFIED
    assert req["expiration"] == 1780917192


def test_string_expiration_is_coerced_to_int():
    req = {"type_time": ORDER_TIME_GTC}
    apply_expiration(req, {"expiration": "1780917192"})
    assert req["expiration"] == 1780917192
    assert isinstance(req["expiration"], int)


def test_returns_the_same_dict_for_chaining():
    req = {"type_time": ORDER_TIME_GTC}
    assert apply_expiration(req, {"expiration": 1780917192}) is req
