# Health, kill switch, reconcile, metrics

- **`GET /health/live`** — checks only process liveness. No auth required.
- **`GET /health/ready`** — `200` when the terminal and account answer, `503`
  otherwise. An engaged kill switch does **not** make it fail (since 0.3.14): the
  state is reported as `kill_switch_active`, so a `service_healthy` dependant such
  as qkt can still restart while trading is halted. Use this for orchestrator
  healthchecks and for qkt's `depends_on: condition: service_healthy` (see
  [Using with qkt](../connect/qkt.md)).
- **`GET /health`** — full status including `mt5_status`, `version`, `last_error`
  and `server_time` (the broker UTC offset in force, its source and age). Needs the
  API key.
- **`GET /metrics`** — Prometheus text format; needs the API key. Series:
  `mt5_connected`, `mt5_reconnects_total`, `kill_switch_active`,
  `reconciliation_discrepancies_total`, `orders_submitted_total`,
  `orders_failed_total`, `http_request_duration_seconds`,
  `mt5_order_send_duration_seconds`.
- **`POST /kill`** — halts trading. Writes the file at `KILL_SWITCH_FILE`
  (default `/config/kill-switch`); its mere existence is the active state, so it
  survives a restart. `POST /kill?flatten=true` also removes pending orders and
  closes every open position. While engaged, `/order`, `/modify_sl_tp`,
  `/close_position`, `/position_close_partial` and `/close_all_positions` return
  `423`.
- **`POST /kill/release`** — resumes trading by removing that file.
- **`GET /reconcile?magic=...`** — returns broker positions, orders, and
  the last 24 hours of deals (all of them when `magic` is omitted), so a strategy can recover its true
  state after a restart or a `502 unknown_outcome`.

GTD ("good-till-date") order expiries (the `expiration` field, unix seconds) are
converted from UTC to broker-server time. The offset comes, in order, from
`MT5_SERVER_TIME_ZONE`, then `MT5_SERVER_UTC_OFFSET_SECONDS`, then a value derived
from the freshest live Market Watch quote (any broker symbol naming works). The
derived value is refreshed every `MT5_TIME_REFRESH_SECONDS` while connected, and
a changed reading is adopted only after `MT5_TIME_OFFSET_CONFIRMATIONS` agreeing
reads, so a stalled feed cannot move it. Check what is in force under `server_time`
in `GET /health`. See [Configuration](../reference/configuration.md). If no
explicit setting and no usable derived offset exist, a GTD order is rejected
rather than expiring at the wrong time.

## Connection recovery

If the terminal dies, the gateway relaunches it and logs it in with the configured
credentials. Failed reconnects back off (`MT5_RECONNECT_COOLDOWN_SECONDS`, doubling
up to `MT5_RECONNECT_COOLDOWN_MAX_SECONDS`) and requests fail fast meanwhile instead
of each starting another `initialize()`.
