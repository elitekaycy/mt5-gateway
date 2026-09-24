"""Time-in-force handling for MT5 order requests.

MT5 pending orders default to ORDER_TIME_GTC ("good-till-cancelled"): they rest on
the book until filled or explicitly removed. When a caller wants the broker itself
to drop an unfilled order at a set time ("good-till-date" / GTD), it passes an
``expiration`` (unix epoch seconds) in the request, which switches the order to
ORDER_TIME_SPECIFIED so MT5 expires it automatically.

Kept in its own module (importing only MetaTrader5) so the logic is unit-testable
on Linux CI with a stubbed mt5, without pulling in Flask and the rest of the app.
"""

import os
import time
from collections.abc import Callable
from typing import Optional

from mt5_connection import mt5
from time_utils import derive_from_tick, offset_usable_for_gtd, utc_epoch_to_server


def derive_from_live_quote(
    symbol: str, read_tick_ms: Callable[[], Optional[int]]
) -> Optional[int]:
    """Derive the broker offset from [symbol]'s quote once it is seen to move.

    Reads the tick up to ``MT5_TIME_ORDER_DERIVE_ATTEMPTS`` times (default 5),
    ``MT5_TIME_ORDER_DERIVE_DELAY`` seconds apart (default 0.2). A quote that never
    advances may be stale by whole hours, so it derives nothing.

    Returns:
        The offset the live quote implies, or None when no read showed it moving.
    """
    attempts = int(os.getenv("MT5_TIME_ORDER_DERIVE_ATTEMPTS", "5"))
    delay = float(os.getenv("MT5_TIME_ORDER_DERIVE_DELAY", "0.2"))
    previous = read_tick_ms()
    for _ in range(attempts - 1):
        if delay > 0:
            time.sleep(delay)
        current = read_tick_ms()
        if current and previous and current > previous:
            return derive_from_tick(symbol, current / 1000)
        previous = current
    return None


def apply_expiration(
    request_data, data, existing_order=None, symbol=None, read_tick_ms=None
):
    """Upgrade an order request to GTD when the caller supplied an expiration.

    Reads ``expiration`` (unix epoch seconds) from the incoming request ``data``.
    If present, sets the MT5 request to expire at that time (ORDER_TIME_SPECIFIED);
    if absent, leaves the request untouched so it keeps the time-in-force it already
    has (the GTC default) — existing callers are unaffected.

    The broker offset normally comes from the cache the connection keeps fresh. Only when
    no usable offset exists does the order derive one from its own ``symbol``:
    ``read_tick_ms`` returns that symbol's latest tick in epoch milliseconds, and it is
    read until the quote moves (see ``derive_from_live_quote``). Without a live quote the
    conversion refuses the order rather than guessing.

    Mutates ``request_data`` in place and returns it.

    e.g. data={"expiration": 1780917192} -> request_data gains
         type_time=ORDER_TIME_SPECIFIED and expiration=1780917192 (expires at that
         unix time). data={} -> request_data unchanged.
    """
    expiration = data.get("expiration")
    if expiration is not None:
        if (
            symbol is not None
            and read_tick_ms is not None
            and not offset_usable_for_gtd()
        ):
            derive_from_live_quote(symbol, read_tick_ms)
        request_data["type_time"] = mt5.ORDER_TIME_SPECIFIED
        request_data["expiration"] = utc_epoch_to_server(expiration)
    elif existing_order is not None:
        request_data["type_time"] = existing_order.type_time
        if getattr(existing_order, "time_expiration", 0):
            request_data["expiration"] = existing_order.time_expiration
    return request_data
