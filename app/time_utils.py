"""Broker-server time and UTC conversion in one explicit boundary.

MT5 reports and expects timestamps in *broker-server* time, which is rarely UTC
(most MT5 servers run EET, i.e. UTC+2 in winter / UTC+3 in summer). Converting a
GTD expiry the wrong way makes the broker drop the order hours early, or reject it
outright (retcode 10022) when the mis-shifted deadline lands in the past.

The offset is resolved in priority order: an explicit ``MT5_SERVER_TIME_ZONE`` or
``MT5_SERVER_UTC_OFFSET_SECONDS`` always wins; otherwise a value derived from a live broker
quote, one whose tick advanced between two reads (see ``live_tick`` and
``derive_from_tick``); otherwise it is unknown. When it is unknown, outbound conversion
fails loud rather than silently assuming UTC.
"""

import logging
import os
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ENV_VAR = "MT5_SERVER_UTC_OFFSET_SECONDS"
_ZONE_ENV_VAR = "MT5_SERVER_TIME_ZONE"
_MAX_AGE_ENV_VAR = "MT5_TIME_MAX_OFFSET_AGE_SECONDS"
_CONFIRMATIONS_ENV_VAR = "MT5_TIME_OFFSET_CONFIRMATIONS"
_DEFAULT_CONFIRMATIONS = 2
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
# A live reading that disagrees with the cached offset, and how many times in a row it
# has been seen. It replaces the cache only once confirmed.
_pending_offset_seconds: Optional[int] = None
_pending_count = 0


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
    """Cache an offset derived from broker server time; pass None to clear it.

    Either way any unconfirmed candidate is dropped.
    """
    global _derived_offset_seconds, _derived_symbol, _derived_at
    global _pending_offset_seconds, _pending_count
    _pending_offset_seconds = None
    _pending_count = 0
    _derived_offset_seconds = seconds
    _derived_symbol = symbol if seconds is not None else None
    if seconds is None:
        _derived_at = None
    else:
        _derived_at = float(derived_at) if derived_at is not None else time.time()


def max_offset_age_seconds() -> int:
    """How old a derived offset may be before GTD conversion stops trusting it."""
    return int(os.getenv(_MAX_AGE_ENV_VAR, str(_DEFAULT_MAX_AGE_SECONDS)))


def offset_confirmations() -> int:
    """How many live readings in a row a new value needs before it replaces the cache."""
    return max(1, int(os.getenv(_CONFIRMATIONS_ENV_VAR, str(_DEFAULT_CONFIRMATIONS))))


def offset_usable_for_gtd(now: Optional[Union[int, float]] = None) -> bool:
    """True when a GTD conversion would succeed without deriving first.

    That is an explicit zone or seconds setting, or a derived value younger than
    ``MT5_TIME_MAX_OFFSET_AGE_SECONDS``.
    """
    moment = float(now) if now is not None else time.time()
    if _zone_offset_seconds(moment) is not None or _env_offset_seconds() is not None:
        return True
    if _derived_offset_seconds is None or _derived_at is None:
        return False
    return moment - _derived_at <= max_offset_age_seconds()


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
    """Derive the offset from a live quote on [symbol] and cache it.

    Callers pass only quotes proven live (see ``live_tick``): a frozen quote repeats its
    last tick and can be stale by close to a whole number of hours, which would round to
    a wrong offset. Any symbol that quotes on the account will do. A value that rounds
    unclean is ignored and leaves the cache as it was.

    A value that differs from the cached one replaces it only after
    ``MT5_TIME_OFFSET_CONFIRMATIONS`` readings in a row (default 2); each disagreement and
    the switch itself log a WARNING. A DST change is adopted one refresh later, a one-off
    bad reading never. A reading that agrees with the cache refreshes it and drops any
    candidate.

    Returns:
        The offset this quote implies, or None when it was missing or rounded unclean.
    """
    global _pending_offset_seconds, _pending_count
    if not tick_time:
        return None
    now = float(utc_now) if utc_now is not None else time.time()
    derived = derive_offset_from_server_epoch(tick_time, now)
    if derived is None:
        return None
    previous = _derived_offset_seconds
    if previous is None or previous == derived:
        set_derived_offset(derived, symbol=symbol, derived_at=now)
        return derived
    if _pending_offset_seconds == derived:
        _pending_count += 1
    else:
        _pending_offset_seconds = derived
        _pending_count = 1
    needed = offset_confirmations()
    if _pending_count >= needed:
        logger.warning(
            "broker UTC offset changed %d -> %d (source=%s, %d readings)",
            previous,
            derived,
            symbol,
            _pending_count,
        )
        set_derived_offset(derived, symbol=symbol, derived_at=now)
    else:
        logger.warning(
            "broker UTC offset reading %d disagrees with %d (source=%s); keeping %d "
            "until confirmed (%d/%d)",
            derived,
            previous,
            symbol,
            previous,
            _pending_count,
            needed,
        )
    return derived


def tick_time_ms(tick: Any) -> Optional[int]:
    """A tick's time in epoch milliseconds, or None when there is no tick.

    Uses ``time_msc`` when the terminal reports it and falls back to ``time`` seconds,
    so two reads inside the same second can still show a quote moving.
    """
    if tick is None:
        return None
    msc = getattr(tick, "time_msc", None)
    if msc:
        return int(msc)
    seconds = getattr(tick, "time", None)
    return int(seconds) * 1000 if seconds else None


def live_tick(
    before: Mapping[str, Optional[int]],
    after: Mapping[str, Optional[int]],
) -> Optional[tuple[str, int]]:
    """The freshest (symbol, tick_ms) whose quote advanced between two reads.

    A quote that did not move proves nothing about its age, so it is never a
    candidate, however recent it looks. Missing or zero times are ignored.

    e.g. before={"A": 1000, "B": 9000}, after={"A": 1250, "B": 9000} -> ("A", 1250).
    """
    best: Optional[tuple[str, int]] = None
    for symbol, tick_ms in after.items():
        previous = before.get(symbol)
        if not tick_ms or not previous or tick_ms <= previous:
            continue
        if best is None or tick_ms > best[1]:
            best = (symbol, int(tick_ms))
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
