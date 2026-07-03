"""Time-in-force handling for MT5 order requests.

MT5 pending orders default to ORDER_TIME_GTC ("good-till-cancelled"): they rest on
the book until filled or explicitly removed. When a caller wants the broker itself
to drop an unfilled order at a set time ("good-till-date" / GTD), it passes an
``expiration`` (unix epoch seconds) in the request, which switches the order to
ORDER_TIME_SPECIFIED so MT5 expires it automatically.

Kept in its own module (importing only MetaTrader5) so the logic is unit-testable
on Linux CI with a stubbed mt5, without pulling in Flask and the rest of the app.
"""

from mt5_connection import mt5
from time_utils import utc_epoch_to_server


def apply_expiration(request_data, data, existing_order=None):
    """Upgrade an order request to GTD when the caller supplied an expiration.

    Reads ``expiration`` (unix epoch seconds) from the incoming request ``data``.
    If present, sets the MT5 request to expire at that time (ORDER_TIME_SPECIFIED);
    if absent, leaves the request untouched so it keeps the time-in-force it already
    has (the GTC default) — existing callers are unaffected.

    Mutates ``request_data`` in place and returns it.

    e.g. data={"expiration": 1780917192} -> request_data gains
         type_time=ORDER_TIME_SPECIFIED and expiration=1780917192 (expires at that
         unix time). data={} -> request_data unchanged.
    """
    expiration = data.get("expiration")
    if expiration is not None:
        request_data["type_time"] = mt5.ORDER_TIME_SPECIFIED
        request_data["expiration"] = utc_epoch_to_server(expiration)
    elif existing_order is not None:
        request_data["type_time"] = existing_order.type_time
        if getattr(existing_order, "time_expiration", 0):
            request_data["expiration"] = existing_order.time_expiration
    return request_data
