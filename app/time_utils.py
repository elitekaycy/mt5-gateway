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
from datetime import datetime, timezone
from typing import Optional, Union

logger = logging.getLogger(__name__)

_ENV_VAR = "MT5_SERVER_UTC_OFFSET_SECONDS"
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


class ServerOffsetUnavailable(RuntimeError):
    """Raised when a UTC->server conversion is needed but no offset is known."""


def _env_offset_seconds() -> Optional[int]:
    """Return the explicitly configured offset, or None when the env is unset/blank."""
    raw = os.getenv(_ENV_VAR)
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def set_derived_offset(seconds: Optional[int]) -> None:
    """Cache an offset derived from broker server time; pass None to clear it."""
    global _derived_offset_seconds
    _derived_offset_seconds = seconds


def resolve_offset_seconds() -> Optional[int]:
    """Resolve the broker UTC offset: explicit env wins, else the derived value, else None."""
    env = _env_offset_seconds()
    if env is not None:
        return env
    return _derived_offset_seconds


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


def utc_epoch_to_server(epoch: Union[int, float]) -> int:
    """Convert a true UTC epoch to the broker-server epoch expected by MT5.

    Raises:
        ServerOffsetUnavailable: when no offset can be resolved, so a GTD order is
            rejected rather than placed at the wrong time (silently assuming UTC).
    """
    offset = resolve_offset_seconds()
    if offset is None:
        raise ServerOffsetUnavailable(
            "broker UTC offset unknown: set MT5_SERVER_UTC_OFFSET_SECONDS or retry "
            "once a fresh quote is available"
        )
    return int(epoch) + offset
