"""Append-only JSON order audit records."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = (
    "event",
    "client_order_id",
    "mt5_ticket",
    "deal",
    "symbol",
    "side",
    "order_type",
    "volume_requested",
    "volume_filled",
    "price_requested",
    "price_filled",
    "retcode",
    "retcode_name",
    "latency_ms",
    "account_mode",
    "magic",
)


class OrderAuditLog:
    def __init__(self, path=None):
        self.path = Path(
            path or os.getenv("ORDER_AUDIT_FILE", "/config/order-audit.jsonl")
        )
        self._lock = Lock()

    def emit(self, event, **fields):
        record = {field: fields.get(field) for field in REQUIRED_FIELDS}
        record["event"] = event
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                    0o600,
                )
                try:
                    os.write(descriptor, line.encode("utf-8"))
                finally:
                    os.close(descriptor)
        except OSError:
            logger.exception("Unable to append order audit record")


order_audit = OrderAuditLog()
