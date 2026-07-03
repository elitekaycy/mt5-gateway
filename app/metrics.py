"""Small dependency-free Prometheus text registry."""

from collections import defaultdict
from threading import Lock

from flask import Blueprint, Response


class Metrics:
    def __init__(self):
        self._lock = Lock()
        self._values = defaultdict(float)

    def inc(self, name, labels=(), amount=1.0):
        with self._lock:
            self._values[(name, tuple(sorted(labels)))] += amount

    def set(self, name, value, labels=()):
        with self._lock:
            self._values[(name, tuple(sorted(labels)))] = float(value)

    def render(self):
        with self._lock:
            rows = []
            for (name, labels), value in sorted(self._values.items()):
                suffix = ""
                if labels:
                    escaped = ",".join(
                        f'{key}="{str(label).replace(chr(34), chr(92) + chr(34))}"'
                        for key, label in labels
                    )
                    suffix = "{" + escaped + "}"
                rows.append(f"{name}{suffix} {value}")
            return "\n".join(rows) + "\n"


metrics = Metrics()
for metric_name in (
    "mt5_connected",
    "mt5_reconnects_total",
    "kill_switch_active",
    "reconciliation_discrepancies_total",
    "orders_submitted_total",
    "orders_failed_total",
    "http_request_duration_seconds",
    "mt5_order_send_duration_seconds",
):
    metrics.set(metric_name, 0)

metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.get("/metrics")
def prometheus_metrics():
    return Response(metrics.render(), mimetype="text/plain; version=0.0.4")
