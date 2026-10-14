# Configuration

## Core — headless login and API key

Without `MT5_LOGIN`, `MT5_PASSWORD` and `MT5_SERVER`, the gateway starts but stays
logged out until you log in by hand over VNC on `:3000`. `MT5_LOGIN` set with an empty
`MT5_SERVER` or `MT5_PASSWORD` is logged as an invalid env-login config.

| Var | Meaning |
|---|---|
| `MT5_LOGIN` | Broker account number. |
| `MT5_PASSWORD` | Trading password for that account. |
| `MT5_SERVER` | Broker server name (e.g. `Exness-MT5Trial9`), not an IP or file. |
| `API_KEY` | Bearer token required by API operations except `/health/live`. Swagger UI/spec assets stay readable without it so the docs UI can load. Not needed for login, but if it is unset the API runs with **no authentication** and logs a warning at start. |

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
| `MT5_RECONNECT_COOLDOWN_SECONDS` | `5` | After a failed reconnect, requests fail fast for this long before the next `initialize()`; doubles per consecutive failure. |
| `MT5_RECONNECT_COOLDOWN_MAX_SECONDS` | `60` | Cap on the reconnect back-off window. |
| `MT5_LOGIN_FIRST_TRIES` | `36` | Boot login loop: 5-second polls for authorization on the first connect candidate. |
| `MT5_LOGIN_TRIES` | `18` | Boot login loop: 5-second polls for each later candidate. |
| `MT5_CONNECTION_VERIFY_TTL_SECONDS` | `30` | How long a verified-connected status is trusted before the next request re-probes MT5 live. |
| `MT5_FILL_CONFIRM_TIMEOUT_MS` | `3000` | How long a market order, or a close whose acknowledgement carries price `0` or no deal (dealer-desk servers), waits for the executed deal in history before answering. |
| `MT5_FILL_CONFIRM_POLL_MS` | `200` | Poll interval while waiting for that deal. |
| `MT5_IDEMPOTENCY_TTL` | `3600` | Seconds an `Idempotency-Key` is remembered for replay. |

A reconnect after a terminal death logs the relaunched terminal in with the
`MT5_LOGIN` / `MT5_PASSWORD` credentials and the address that authorized at boot. The
API writes `/tmp/mt5-api-session` once it is attached to a logged-in terminal, and the
boot login loop counts that as authorized, so a terminal the API is using is never
killed because its journal line has not landed yet. `MT5_SESSION_MARKER` and
`MT5_LOGIN_SERVER_FILE` override the paths of the two small files the API and the boot
script share (`/tmp/mt5-api-session`, `/tmp/mt5-login-server`); you should not need them.

## Optional — server time & GTD orders

| Var | Default | Meaning |
|---|---|---|
| `MT5_SERVER_TIME_ZONE` | unset | IANA zone of the broker's trade server (e.g. `Europe/Athens`, `Etc/UTC`). Converted per instant, so it stays right across DST. When set it always wins. |
| `MT5_SERVER_UTC_OFFSET_SECONDS` | unset | Fixed broker offset from UTC in seconds (e.g. `10800`). Kept for compatibility; it does not follow DST, prefer `MT5_SERVER_TIME_ZONE`. Wins over derivation. |
| `MT5_TIME_REFERENCE_SYMBOL` | unset | Symbol to try first when deriving the offset. Unset, the gateway uses the freshest live quote among the symbols visible in Market Watch, so any broker naming (`EURUSDm`, `EURUSD.pro`, crypto-only accounts) works with no configuration. |
| `MT5_TIME_DERIVE_ATTEMPTS` | `10` | Reads of the candidate quotes when deriving the offset. Only a quote whose tick advanced since the previous read may derive; a frozen quote (closed market, stalled feed) never does, however recent it looks. |
| `MT5_TIME_DERIVE_DELAY` | `0.5` | Seconds between those polling attempts. |
| `MT5_TIME_REFRESH_SECONDS` | `600` | How often the offset is re-derived while connected (DST switches, markets that were closed at boot). `0` disables the refresh. |
| `MT5_TIME_OFFSET_CONFIRMATIONS` | `2` | Live readings in a row a different value needs before it replaces the cached offset. Each disagreement and the switch log a WARNING. A DST change is adopted one refresh later; a single bad reading never. |
| `MT5_TIME_MAX_OFFSET_AGE_SECONDS` | `21600` | A derived offset older than this is not used for GTD conversion; the order is refused until a fresh quote refreshes it. |
| `MT5_TIME_ORDER_DERIVE_ATTEMPTS` | `5` | When a GTD order finds no usable offset, reads of its own symbol's quote waiting for it to move. |
| `MT5_TIME_ORDER_DERIVE_DELAY` | `0.2` | Seconds between those reads. |

A GTD order uses the cached offset. Only when none is usable does it derive one from its own
symbol, once that quote is seen to move, so a broker whose reference symbols never quote still
places GTD orders correctly.
`GET /health` reports the offset in force under `server_time` (`offset_seconds`, `source`,
`symbol`, `derived_at`, `age_seconds`).

When qkt drives the gateway, qkt does the broker-time to UTC conversion itself and its
docs tell you to keep `MT5_SERVER_UTC_OFFSET_SECONDS=0` on the gateway; see
[Using with qkt](../connect/qkt.md).

If no explicit setting and no usable derived offset exist, a GTD order is
rejected rather than expiring at the wrong time.

## Optional — pre-trade limits

| Var | Default | Meaning |
|---|---|---|
| `SYMBOL_WHITELIST` | unset (no restriction) | Comma-separated symbols orders are allowed against. Empty means any symbol. |
| `MAX_ORDER_VOLUME` | `100` | Maximum lot size accepted per order. |
| `MAX_PRICE_DEVIATION_PCT` | `20` | Maximum allowed deviation between a requested price and the current market price, as a percent. |
| `MAX_ORDER_DEVIATION` | `1000` | Maximum allowed price deviation in points for the broker-side `deviation` field. |

`POST /order` also rejects any body field outside `symbol`, `volume`, `type`, `price`,
`stoplimit`, `sl`, `tp`, `deviation`, `magic`, `comment`, `type_filling`, `expiration`
and `client_order_id`.

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
