"""Resource bounds for data/history endpoints."""

import os
from datetime import datetime


def validate_num_bars(value):
    maximum = int(os.getenv("MAX_NUM_BARS", "10000"))
    count = int(value)
    if not 1 <= count <= maximum:
        raise ValueError(f"num_bars must be between 1 and {maximum}")
    return count


def validate_date_range(start: datetime, end: datetime):
    if start >= end:
        raise ValueError("start must be before end")
    maximum_days = int(os.getenv("MAX_HISTORY_RANGE_DAYS", "31"))
    if (end - start).total_seconds() > maximum_days * 86400:
        raise ValueError(f"date range cannot exceed {maximum_days} days")


def validate_tick_flags(value):
    flags = int(value)
    if not 0 <= flags <= 7:
        raise ValueError("flags must be a valid COPY_TICKS bitmask (0..7)")
    return flags
