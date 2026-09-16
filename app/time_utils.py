"""Broker-server time and UTC conversion in one explicit boundary.

MT5 reports and expects timestamps in *broker-server* time, which is rarely UTC
(most MT5 servers run EET, i.e. UTC+2 in winter / UTC+3 in summer). Converting a
GTD expiry the wrong way makes the broker drop the order hours early, or reject it
outright (retcode 10022) when the mis-shifted deadline lands in the past.

The offset is resolved in priority order: an explicit ``MT5_SERVER_UTC_OFFSET_SECONDS``
env always wins; otherwise a value derived from a fresh broker quote at connect time
(see ``derive_offset_from_server_epoch``); otherwise it is unknown. When it is
unknown, outbound conversion fails loud rather than silently assuming UTC.
"""

import logging
import os
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ENV_VAR = "MT5_SERVER_UTC_OFFSET_SECONDS"
_ZONE_ENV_VAR = "MT5_SERVER_TIME_ZONE"
_MAX_AGE_ENV_VAR = "MT5_TIME_MAX_OFFSET_AGE_SECONDS"
_DEFAULT_MAX_AGE_SECONDS = 6 * 3600
_HOUR = 3600
# A live quote lags server-now by at most a few seconds, so a genuine offset rounds
# to a whole hour with a tiny residual. A stale weekend quote lands far from any hour
# boundary and is rejected, so a wrong offset is never derived.
_FRESHNESS_TOLERANCE_SECONDS = 90
# No real MT5 trade server sits outside this band; a rounded value beyond it means
# the quote was stale by a near-integer number of hours and coincidentally rounded.
_MIN_OFFSET_SECONDS = -12 * _HOUR
_MAX_OFFSET_SECONDS = 14 * _HOUR

_derived_offset_seconds: Optional[int] = None
_derived_symbol: Optional[str] = None
_derived_at: Optional[float] = None


class ServerOffsetUnavailable(RuntimeError):
    """Raised when a UTC->server conversion is needed but no offset is known."""


def _env_offset_seconds() -> Optional[int]:
    """Return the explicitly configured offset, or None when the env is unset/blank."""
    raw = os.getenv(_ENV_VAR)
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _zone_offset_seconds(at_epoch: Union[int, float]) -> Optional[int]:
    """Offset of ``MT5_SERVER_TIME_ZONE`` at [at_epoch], or None when it is unset.

    An IANA zone is converted per instant, so it stays right across DST where a fixed
    seconds value would drift. An unknown zone name is a configuration error and raises.
    """
    name = os.getenv(_ZONE_ENV_VAR)
    if name is None or name.strip() == "":
        return None
    zone = ZoneInfo(name.strip())
    moment = datetime.fromtimestamp(float(at_epoch), tz=timezone.utc)
    delta = zone.utcoffset(moment)
    return int(delta.total_seconds()) if delta is not None else 0


def set_derived_offset(
    seconds: Optional[int],
    symbol: Optional[str] = None,
    derived_at: Optional[float] = None,
) -> None:
    """Cache an offset derived from broker server time; pass None to clear it."""
    global _derived_offset_seconds, _derived_symbol, _derived_at
    _derived_offset_seconds = seconds
    _derived_symbol = symbol if seconds is not None else None
    if seconds is None:
        _derived_at = None
    else:
        _derived_at = float(derived_at) if derived_at is not None else time.time()


def max_offset_age_seconds() -> int:
    """How old a derived offset may be before GTD conversion stops trusting it."""
    return int(os.getenv(_MAX_AGE_ENV_VAR, str(_DEFAULT_MAX_AGE_SECONDS)))


def resolve_offset_seconds(
    at_epoch: Optional[Union[int, float]] = None,
) -> Optional[int]:
    """Resolve the broker UTC offset: zone, else seconds env, else the derived value, else None.

    [at_epoch] is the instant being converted (needed for a zone's DST rule); it
    defaults to now.
    """
    zone = _zone_offset_seconds(at_epoch if at_epoch is not None else time.time())
    if zone is not None:
        return zone
    env = _env_offset_seconds()
    if env is not None:
        return env
    return _derived_offset_seconds


def derive_from_tick(
    symbol: str,
    tick_time: Union[int, float, None],
    utc_now: Optional[Union[int, float]] = None,
) -> Optional[int]:
    """Derive the offset from one quote on [symbol] and cache it when it is fresh.

    Any symbol that quotes on the account will do, which is what makes derivation work
    on brokers with suffixed names or no EUR/USD at all. A stale quote is ignored and
    leaves the cache as it was. A value that differs from the cached one is logged at
    WARNING: that is how a DST switch shows up.

    Returns:
        The derived offset, or None when the quote was missing or stale.
    """
    if not tick_time:
        return None
    now = float(utc_now) if utc_now is not None else time.time()
    derived = derive_offset_from_server_epoch(tick_time, now)
    if derived is None:
        return None
    previous = _derived_offset_seconds
    if previous is not None and previous != derived:
        logger.warning(
            "broker UTC offset changed %d -> %d (source=%s)", previous, derived, symbol
        )
    set_derived_offset(derived, symbol=symbol, derived_at=now)
    return derived


def freshest_tick(
    ticks: Iterable[tuple[str, Union[int, float, None]]],
) -> Optional[tuple[str, int]]:
    """The (symbol, tick_time) with the latest time, ignoring missing or zero times."""
    best: Optional[tuple[str, int]] = None
    for symbol, tick_time in ticks:
        if not tick_time:
            continue
        if best is None or tick_time > best[1]:
            best = (symbol, int(tick_time))
    return best


def offset_status(now: Optional[Union[int, float]] = None) -> dict[str, Any]:
    """What `/health` reports: the offset in force, where it came from, and its age."""
    moment = float(now) if now is not None else time.time()
    zone = _zone_offset_seconds(moment)
    if zone is not None:
        return _status(zone, "zone", None, None, None)
    env = _env_offset_seconds()
    if env is not None:
        return _status(env, "env", None, None, None)
    if _derived_offset_seconds is None or _derived_at is None:
        return _status(None, None, None, None, None)
    derived_at = datetime.fromtimestamp(_derived_at, tz=timezone.utc)
    return _status(
        _derived_offset_seconds,
        "derived",
        _derived_symbol,
        derived_at.isoformat().replace("+00:00", "Z"),
        int(moment - _derived_at),
    )


def _status(
    offset: Optional[int],
    source: Optional[str],
    symbol: Optional[str],
    derived_at: Optional[str],
    age: Optional[int],
) -> dict[str, Any]:
    return {
        "offset_seconds": offset,
        "source": source,
        "symbol": symbol,
        "derived_at": derived_at,
        "age_seconds": age,
    }


def derive_offset_from_server_epoch(
    server_epoch: Union[int, float], utc_now: Union[int, float]
) -> Optional[int]:
    """Derive a whole-hour broker offset from a fresh server quote time.

    Args:
        server_epoch: Epoch seconds of a broker quote, expressed in server time
            (e.g. ``symbol_info_tick(symbol).time``).
        utc_now: The true current UTC epoch seconds (e.g. ``time.time()``).

    Returns:
        The offset in seconds rounded to the nearest hour, or None when the quote
        is too stale to trust (its delta does not round cleanly to an hour) or the
        result is implausible for any broker server.

    e.g. a UTC+3 server just quoted, ``utc_now`` now -> 10800; a quote 2.5h stale
    -> None.
    """
    delta = float(server_epoch) - float(utc_now)
    rounded = round(delta / _HOUR) * _HOUR
    if abs(delta - rounded) > _FRESHNESS_TOLERANCE_SECONDS:
        return None
    if not _MIN_OFFSET_SECONDS <= rounded <= _MAX_OFFSET_SECONDS:
        return None
    return int(rounded)


def parse_iso_utc(value: str) -> datetime:
    """Parse ISO-8601 input; naive values are defined as UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def server_epoch_to_utc(epoch: Union[int, float]) -> datetime:
    """Convert an MT5 broker-server epoch to an aware UTC datetime.

    A read/display path: when the offset is unknown it degrades to the raw server
    epoch rather than failing, so history and deal reporting keep working.
    """
    offset = resolve_offset_seconds()
    if offset is None:
        offset = 0
    adjusted = float(epoch) - offset
    return datetime.fromtimestamp(adjusted, tz=timezone.utc)


def utc_epoch_to_server(
    epoch: Union[int, float],
    utc_now: Optional[Union[int, float]] = None,
) -> int:
    """Convert a true UTC epoch to the broker-server epoch expected by MT5.

    An explicit zone or seconds setting always applies. A derived offset applies only
    while it is younger than ``MT5_TIME_MAX_OFFSET_AGE_SECONDS``; past that it may sit
    on the wrong side of a DST switch, so the conversion refuses instead of guessing.

    Raises:
        ServerOffsetUnavailable: when no offset can be resolved, so a GTD order is
            rejected rather than placed at the wrong time (silently assuming UTC).
    """
    explicit = _zone_offset_seconds(epoch)
    if explicit is None:
        explicit = _env_offset_seconds()
    if explicit is not None:
        return int(epoch) + explicit
    now = float(utc_now) if utc_now is not None else time.time()
    if _derived_offset_seconds is None or _derived_at is None:
        raise ServerOffsetUnavailable(
            "broker UTC offset unknown: no fresh broker quote to derive it from; set "
            "MT5_SERVER_TIME_ZONE or retry once a symbol on this account quotes"
        )
    age = now - _derived_at
    if age > max_offset_age_seconds():
        raise ServerOffsetUnavailable(
            f"broker UTC offset is {int(age)}s old (max {max_offset_age_seconds()}s) and no "
            "fresh quote refreshed it; set MT5_SERVER_TIME_ZONE or retry once a symbol quotes"
        )
    return int(epoch) + _derived_offset_seconds
