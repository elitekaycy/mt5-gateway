"""Broker-server time and UTC conversion in one explicit boundary."""

import os
from datetime import datetime, timezone
from typing import Union


def server_utc_offset_seconds() -> int:
    """Return the configured broker-server offset from UTC."""
    return int(os.getenv("MT5_SERVER_UTC_OFFSET_SECONDS", "0"))


def parse_iso_utc(value: str) -> datetime:
    """Parse ISO-8601 input; naive values are defined as UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def server_epoch_to_utc(epoch: Union[int, float]) -> datetime:
    """Convert an MT5 broker-server epoch to an aware UTC datetime."""
    adjusted = float(epoch) - server_utc_offset_seconds()
    return datetime.fromtimestamp(adjusted, tz=timezone.utc)


def utc_epoch_to_server(epoch: Union[int, float]) -> int:
    """Convert a true UTC epoch to the broker-server epoch expected by MT5."""
    return int(epoch) + server_utc_offset_seconds()
