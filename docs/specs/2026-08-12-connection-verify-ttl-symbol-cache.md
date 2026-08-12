# Per-request IPC reduction — connection verify TTL and symbol-select cache

Date: 2026-08-12
Status: implemented
Scope: `mt5-gateway` (`app/mt5_connection.py`, `app/lib.py`, `app/routes/symbol.py`)

## Problem

Every HTTP request paid 3 serialized MT5 IPC calls through the process-global
`SerializedMT5` RLock:

1. `require_mt5_connection` → `ensure_connection()` ran a live
   `mt5.account_info()` probe on **every** request.
2. `validate_symbol` ran `mt5.symbol_select(symbol, True)` on every tick/info
   request, even for symbols already in Market Watch.
3. The route's actual call (e.g. `mt5.symbol_info_tick`).

At ~110 req/s from a 25-strategy client the lock saturates: waitress queue
depth grows, RTTs spike to seconds, clients time out and retry (amplifying
load), and downstream market data goes stale.

## Goals

- Steady-state cost of read-only endpoints is **one** serialized MT5 IPC call:
  - `GET /symbol_info_tick/<symbol>`: 3 → 1 (`symbol_info_tick`)
  - `GET /symbol_info/<symbol>`: 3 → 1 (`symbol_info`)
  - `GET /account`: 2 → 1 (`account_info`)
  - `GET /get_positions`: 3 → 2 (`positions_total` + `positions_get`; the
    endpoint's own two calls are unchanged)
  - `GET /orders`: 2 → 1 (`orders_get`)
- Failure semantics are not weakened: terminal disconnects are still detected
  within a bounded time and still trigger the full reconnect + `reconcile()`
  path.

## Design

### Connection verification TTL (`MT5Connection.ensure_connection`)

- While status is CONNECTED, `ensure_connection()` trusts the cached state and
  performs **no** IPC call. A live `mt5.account_info()` probe runs at most once
  per `MT5_CONNECTION_VERIFY_TTL_SECONDS` window (default 30, `0` restores the
  old probe-every-request behaviour).
- The probe is serialized on a dedicated `_verify_lock` with a double-checked
  freshness test, so a burst of concurrent requests pays for a single probe per
  TTL window. A failed probe (None or exception) marks the connection
  DISCONNECTED and falls through to the existing reconnect path
  (`MT5_RECONNECT_ATTEMPTS`, exponential backoff from
  `MT5_RECONNECT_BASE_DELAY`, `reconcile()` after reconnect) — unchanged.
- A successful (re)connect refreshes the verification timestamp
  (`_set_status(CONNECTED)`), so a freshly reconciled session is not
  immediately re-probed.

### Failure-triggered disconnect detection

The TTL bounds worst-case *passive* detection, but a dropped terminal is
usually noticed by an active call first. `SerializedMT5` already reads
`last_error()` at the serialized boundary whenever a call returns None. It now
additionally classifies the error: MetaTrader5 internal/IPC failure codes are
`<= -10000` (`RES_E_INTERNAL_FAIL`, `_SEND`, `_RECEIVE`, `_INIT`, `_CONNECT`,
`_TIMEOUT`). On such an error it invokes a connection-failure callback, wired
at module import to `MT5Connection.note_connection_failure()`, which flips the
status to DISCONNECTED. The next request's `ensure_connection()` then runs the
full reconnect-and-reconcile path.

Benign None results (e.g. `symbol_info_tick` for an unselected symbol,
`history_deals_get` with no matches) carry non-IPC error codes and do **not**
flip the connection state.

Combined detection bound: an IPC-level failure is reflected in connection
status immediately at the serialized boundary; any residual silent-drop case is
caught by the TTL probe within `MT5_CONNECTION_VERIFY_TTL_SECONDS`.

`/health/ready` is untouched: it still performs real `terminal_info()` +
`account_info()` round trips on every poll (it is the Docker healthcheck and
runs at probe frequency, not request frequency).

### Symbol-select cache (`lib.validate_symbol`)

- Successful `symbol_select(symbol, True)` outcomes are cached per symbol in a
  bounded (512 entries, FIFO eviction), lock-guarded module-level cache.
  Symbols are stable for a container's lifetime, so a hit skips the IPC call
  entirely.
- Only successes are cached. Invalid/unselectable symbols are rejected exactly
  as today, with the same `symbol_select` call each time (no negative caching,
  so a symbol that becomes available later is picked up immediately).
- Recovery preserved: today every request re-selects before reading, so a
  symbol dropped from Market Watch (e.g. by a terminal restart) self-heals on
  the next request. With the cache, a None `symbol_info_tick`/`symbol_info`
  result for a cached symbol now evicts it (`invalidate_symbol`), so the next
  request re-selects — the observable behaviour (one 404, then recovery) is
  identical to today.

### Locking invariants

Every `mt5.*` call remains inside the `SerializedMT5` RLock; `last_error()` is
still read at the serialized boundary; the failure callback runs inside that
boundary and performs no MT5 calls itself. No new concurrency is introduced.

## Non-goals

- No change to endpoint response shapes, auth, or order/position semantics.
- No negative caching of invalid symbols.
- No batching/coalescing of the route's own data calls.
- `GET /get_positions` keeps its `positions_total` + `positions_get` pair
  (dropping the pre-check would change error-vs-empty semantics; out of scope).

## Tests

- `tests/test_mt5_connection.py`: TTL caching of the probe, single probe under
  concurrency, failed probe → reconnect path, IPC-failure callback marking the
  connection disconnected, non-IPC None results not affecting status.
- `tests/test_symbol_cache.py`: successful select cached, failures not cached,
  invalidation forces re-select, bounded eviction.
