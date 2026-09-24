# Server offset from live quotes only

Related: `2026-09-15-broker-agnostic-server-offset.md` (#93), #70 (stale tick at connect).

## Problem

The derived broker offset trusts one tick read: `round((tick_time - utc_now) / 1h)` is
accepted when the residual is under 90 s. A quote that is stale by close to a whole number
of hours passes that test and becomes an offset. On 2026-09-23 the host lost its network
around 19:35 UTC; at 19:37:17 the refresher derived `-3600` on an Exness account whose
server runs UTC. Every bar was then labelled an hour ahead (the newest M1 bar read 21:36
at 20:36 UTC), a qkt `bars` request for the last minutes returned nothing, and the value
would have stayed in force for its six-hour life. Ticks kept flowing, so nothing looked
wrong until a consumer asked for recent bars. The same single-read rule applies on every
GTD order.

## Behaviour

A quote derives an offset only when it is proven live: its tick time (`time_msc`, else
`time * 1000`) must have advanced between two reads. A stalled feed repeats its last tick
and so can never derive, whatever its age.

- Refresh (connect, and every `MT5_TIME_REFRESH_SECONDS`): each of the up to
  `MT5_TIME_DERIVE_ATTEMPTS` reads is compared with the previous one; the freshest symbol
  whose tick advanced derives the offset. The first read is only a baseline.
- GTD orders: the cached offset is used as-is. Only when no usable offset exists (no
  zone/seconds setting and no derived value younger than `MT5_TIME_MAX_OFFSET_AGE_SECONDS`)
  does the order read its own symbol's tick until it advances, at most
  `MT5_TIME_ORDER_DERIVE_ATTEMPTS` (default 5) reads `MT5_TIME_ORDER_DERIVE_DELAY`
  (default 0.2 s) apart. Without a live quote the order is refused as today.
- A live quote that disagrees with the cached offset does not replace it at once. The new
  value must be derived `MT5_TIME_OFFSET_CONFIRMATIONS` times in a row (default 2) before
  it is adopted; a derivation that agrees with the cache clears the candidate. Each
  disagreement logs a WARNING with both values, and the switch logs one too. A real DST
  change is adopted one refresh later; a one-off bad reading is dropped.
- The first derivation (nothing cached) needs only one live quote.

Explicit `MT5_SERVER_TIME_ZONE` / `MT5_SERVER_UTC_OFFSET_SECONDS` still win and are
unaffected. `/health` keeps its shape.

## Out of scope

Persisting the derived value across restarts; sub-hour offsets.
