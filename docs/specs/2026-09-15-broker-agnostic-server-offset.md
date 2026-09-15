# Broker-agnostic, DST-safe server UTC offset

Issue: #93. Related: #64 (silent UTC default), #70 (stale tick at connect).

## Problem

MT5 expects GTD `expiration` in broker-server time. The gateway derives the server's UTC
offset once per connect from a quote on `MT5_TIME_REFERENCE_SYMBOL`, default `EURUSD`.
Brokers name symbols differently (`EURUSDm`, `EURUSD.pro`, none at all), so on those
accounts the offset is never derived and every GTD order is refused. When the offset is
derived, it is never refreshed, so a long-lived connection places expiries an hour off
after a DST switch.

## Behaviour

Offset sources, in priority order:

1. `MT5_SERVER_TIME_ZONE` (IANA name). Converted per instant with `zoneinfo`, so it is
   DST-correct. Recommended override.
2. `MT5_SERVER_UTC_OFFSET_SECONDS`. Fixed seconds; kept for compatibility, DST-fragile.
3. Derived from broker quotes, cached with the symbol and the time it was derived.

Derivation:

- At connect: try `MT5_TIME_REFERENCE_SYMBOL` when set; otherwise read every visible
  Market Watch symbol and use the freshest quote. Poll up to `MT5_TIME_DERIVE_ATTEMPTS`
  times, `MT5_TIME_DERIVE_DELAY` seconds apart. Falls back to `EURUSD` only when Market
  Watch cannot be listed.
- At every GTD request: the order's own symbol was just validated, so its tick is read
  and, when fresh, derives the offset for this request and refreshes the cache.
- Every `MT5_TIME_REFRESH_SECONDS` (default 600, 0 disables) while connected: re-derive
  in a daemon thread. A changed value logs a WARNING with old and new offsets.

Staleness: a derived value older than `MT5_TIME_MAX_OFFSET_AGE_SECONDS` (default 21600)
is not used for GTD conversion. With no explicit setting and no usable derived value,
GTD placement is refused with the existing loud 400. UTC is never assumed.

Reads (deal and bar timestamps) keep degrading to the raw server epoch when nothing is
known; they never fail.

`GET /health` reports `server_time`: `offset_seconds`, `source` (`zone`, `env`,
`derived` or `null`), `symbol`, `derived_at` and `age_seconds`.

## Out of scope

Sub-hour offsets (no known MT5 server uses them); persisting the derived value across
container restarts.
