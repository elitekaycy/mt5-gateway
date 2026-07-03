"""Broker-truth snapshots used after ambiguous outcomes and reconnects."""

from datetime import datetime, timedelta, timezone

from mt5_connection import mt5


def reconcile(magic=None, lookback_hours=24):
    """Return current positions/orders and recent deals, optionally by magic."""
    start = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    end = datetime.now(timezone.utc)
    positions = mt5.positions_get()
    orders = mt5.orders_get()
    deals = mt5.history_deals_get(start, end)
    if positions is None or orders is None or deals is None:
        raise RuntimeError(f"MT5 reconciliation failed: {mt5.last_call_error()}")

    def serialize(values):
        rows = [value._asdict() for value in values]
        if magic is not None:
            rows = [row for row in rows if row.get("magic") == magic]
        return rows

    return {
        "as_of": end.isoformat(),
        "magic": magic,
        "positions": serialize(positions),
        "orders": serialize(orders),
        "deals": serialize(deals),
        "discrepancies": [],
    }
