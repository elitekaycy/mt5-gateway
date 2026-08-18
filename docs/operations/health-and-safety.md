# Health, kill switch, reconcile, metrics

- **`GET /health/live`** — checks only process liveness. No auth required.
- **`GET /health/ready`** — requires a connected MT5 account and an inactive
  kill switch. Use this for orchestrator healthchecks and for qkt's
  `depends_on: condition: service_healthy` (see
  [Using with qkt](../connect/qkt.md)).
- **`GET /metrics`** — Prometheus-compatible safety/connection counters.
- **`POST /kill`** — halts trading. Writes the file at `KILL_SWITCH_FILE`
  (default `/config/kill-switch`); its mere existence is the active state.
- **`POST /kill/release`** — resumes trading by removing that file.
- **`GET /reconcile?magic=...`** — returns broker positions, orders, and
  recent deals for a given magic number, so a strategy can recover its true
  state after a restart or a `502 unknown_outcome`.

GTD ("good-till-date") order expiries are converted from UTC to broker-server
time using an offset auto-derived from a live quote at each connect (so it
re-derives across DST). Pin it with `MT5_SERVER_UTC_OFFSET_SECONDS` to
override — see [Configuration](../reference/configuration.md). If neither
the env var nor a fresh quote yields an offset, a GTD order is rejected
rather than expiring at the wrong time.
