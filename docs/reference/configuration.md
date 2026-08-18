# Configuration

## Core — required for headless login

Without these four, the gateway starts but stays logged out until you log in
by hand over VNC on `:3000`.

| Var | Meaning |
|---|---|
| `MT5_LOGIN` | Broker account number. |
| `MT5_PASSWORD` | Trading password for that account. |
| `MT5_SERVER` | Broker server name (e.g. `Exness-MT5Trial9`), not an IP or file. |
| `API_KEY` | Bearer token required by API operations except `/health/live`. Swagger UI/spec assets stay readable without it so the docs UI can load. |

## Optional — connection & resolution tuning

| Var | Default | Meaning |
|---|---|---|
| `MT5_ENABLE_ALGO_TRADING` | `1` | Set to `0`, `false`, `no`, `off`, or `disabled` to boot headless with MT5 Expert/live trading disabled. |
| `MT5_SERVER_ADDR` | unset | Explicit `host:port` to skip name resolution entirely. |
| `MT5_AUTORESOLVE` | `1` | Set `0` to disable resolution (name-only login against a baked/persisted `servers.dat`). |
| `MT5_RESOLVER_URL` | `https://mt5.mtapi.io,http://mt5-resolver:80` | Comma-separated resolver service URLs, tried in order after the baked broker table. |
| `MT5_SETUP_URL` | unset | Broker-branded installer URL, for brokers whose terminal isn't in the baked image. |
| `MT5_SETUP_SHA256` | unset | Required checksum for `MT5_SETUP_URL` — the install refuses to run without it. |
| `MT5_SETUP_ATTEMPTS` | `3` | Retries for a stuck/failed installer download+run. |
| `MT5_SETUP_TIMEOUT` | `600` | Seconds before one install attempt is killed and retried. |
| `MT5_API_PORT` | `5001` | Port the Flask API listens on inside the container. |
| `MT5_RECONNECT_ATTEMPTS` | `3` | Reconnect attempts after a detected MT5 disconnect before giving up. |
| `MT5_RECONNECT_BASE_DELAY` | `1.0` | Base seconds for reconnect backoff. |
| `MT5_CONNECTION_VERIFY_TTL_SECONDS` | `30` | How long a verified-connected status is trusted before the next request re-probes MT5 live. |

## Optional — server time & GTD orders

| Var | Default | Meaning |
|---|---|---|
| `MT5_SERVER_UTC_OFFSET_SECONDS` | auto-derived | Broker server-clock offset from UTC, in seconds (e.g. `10800` for UTC+3/EEST). Used to place GTD ("good-till-date") order expiries at the right instant. If unset, it's derived from a live quote at each connect (so it re-derives across DST); if set, it always overrides auto-derivation. |
| `MT5_TIME_REFERENCE_SYMBOL` | `EURUSD` | Symbol whose live quote auto-derives the server UTC offset at connect. Set it to any symbol your broker quotes if `EURUSD` is unavailable. |
| `MT5_TIME_DERIVE_ATTEMPTS` | `10` | Polling attempts for a fresh-enough quote when deriving the offset. |
| `MT5_TIME_DERIVE_DELAY` | `0.5` | Seconds between those polling attempts. |

If neither the env var nor a fresh quote yields an offset, a GTD order is
rejected rather than expiring at the wrong time.

## Optional — pre-trade limits

| Var | Default | Meaning |
|---|---|---|
| `SYMBOL_WHITELIST` | unset (no restriction) | Comma-separated symbols orders are allowed against. Empty means any symbol. |
| `MAX_ORDER_VOLUME` | `100` | Maximum lot size accepted per order. |
| `MAX_PRICE_DEVIATION_PCT` | `20` | Maximum allowed deviation between a requested price and the current market price, as a percent. |
| `MAX_ORDER_DEVIATION` | `1000` | Maximum allowed price deviation in points for the broker-side `deviation` field. |

## Optional — request/data limits

| Var | Default | Meaning |
|---|---|---|
| `MAX_NUM_BARS` | `10000` | Maximum bars a single `/fetch_data_pos` (or similar) request can return. |
| `MAX_HISTORY_RANGE_DAYS` | `31` | Maximum span a `/fetch_data_range` request can cover. |

## Optional — audit, kill switch, and state paths

| Var | Default | Meaning |
|---|---|---|
| `ORDER_AUDIT_FILE` | `/config/order-audit.jsonl` | Append-only JSON order audit log path. |
| `KILL_SWITCH_FILE` | `/config/kill-switch` | Path whose existence marks the kill switch active — `POST /kill` creates it, `POST /kill/release` removes it. |

## Optional — HTTP surface

| Var | Default | Meaning |
|---|---|---|
| `CORS_ORIGINS` | unset (CORS disabled) | Comma-separated allowed origins. Leave unset unless you're calling the API from a browser. |
| `SWAGGER_SCHEME` | `http` | Scheme Swagger UI uses when building example request URLs. |

## Optional — VNC & logging

| Var | Default | Meaning |
|---|---|---|
| `CUSTOM_USER` / `PASSWORD` | image default | VNC desktop login credentials (`:3000`), for manual login or diagnostics. |
| `LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |

See [Ports & security](ports-and-security.md) for how `API_KEY` and CORS
interact with what's actually exposed.
