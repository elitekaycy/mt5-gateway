"""Query-parameter parsing for the deals-history window.

Kept free of Flask and MetaTrader5 imports so the validation rules are unit-testable
on any platform (same approach as order_time.py).
"""

from datetime import datetime


class DealWindowError(ValueError):
    """Raised when the deals-history query parameters are invalid."""


def parse_deal_window(args):
    """Parse from_date/to_date/position query args.

    Returns (from_timestamp, to_timestamp, position) where position is None when
    the caller wants every deal in the range, e.g. {"from_date": "2026-05-13",
    "to_date": "2026-06-13"} -> (1778976000, 1781654400, None).
    """
    from_date = args.get("from_date")
    to_date = args.get("to_date")
    position = args.get("position")

    if not all([from_date, to_date]):
        raise DealWindowError("from_date and to_date parameters are required")

    try:
        from_date = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        to_date = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        position = int(position) if position is not None else None
    except ValueError as e:
        raise DealWindowError(f"Invalid parameter format: {str(e)}")

    if from_date >= to_date:
        raise DealWindowError("from_date must be before to_date")

    return int(from_date.timestamp()), int(to_date.timestamp()), position
