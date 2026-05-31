# Headless env-driven MT5 login — design

Date: 2026-05-31
Status: approved, pre-implementation
Scope: `mt5-gateway` (impl) + downstream deploy wiring (qkt-prod, qkt templates)

## Problem

The gateway runs MetaTrader 5 under Wine and exposes a REST API. Today the
broker login is a **manual, one-time GUI step**: an operator opens the VNC web
UI and logs MT5 into the broker account by hand. The login then persists in the
`/config` Docker volume and the gateway attaches to it.

Concretely (current behaviour, verified by reading the code and a live gateway):

- `app/app.py:57` calls `MT5Connection.initialize()`, which calls bare
  `mt5.initialize()` with **no credentials** (`app/mt5_connection.py:85`). It
  attaches to whatever account the terminal already auto-logged into.
- The terminal is launched at `scripts/04-install-mt5.sh:25`
  (`wine "$mt5file" &`); it auto-logs-in from the persisted
  `…/MetaTrader 5/Config/accounts.dat` (encrypted server+login+password), with
  `servers.dat`/`terminal.ini`/`common.ini` alongside it, all inside `/config`.
- `app/config.py` reads only `MT5_API_PORT`, `MT5_RECONNECT_ATTEMPTS`,
  `MT5_RECONNECT_BASE_DELAY`, `LOG_LEVEL`. There is no login env var and no
  login route anywhere in the gateway.

So provisioning a new gateway requires a human at a VNC session. We want a fresh
container to **self-log-in from env vars, with AutoTrading enabled, no VNC**,
and to do it consistently across cold boots.

Note: `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` already appear in the *qkt*
root `docker-compose.yml` and several docs, but nothing consumes them — they are
dead wiring. This design makes them real.

## Goals

- A cold-boot gateway (empty `/config`) logs into the broker from env and comes
  up with AutoTrading on, with no GUI interaction.
- Backward compatible: existing gateways with a working `accounts.dat` are
  untouched; env-login is additive and optional.
- Pick the approach that works **consistently** (≥3/3 cold boots, local and on
  the server) by head-to-head test, not by assertion.

## Non-goals

- Replacing the VNC desktop (kept for diagnostics / manual fallback).
- Multi-account-per-terminal. One terminal = one broker account, as today.
- Changing the qkt engine. qkt only talks REST to the gateway; it does not log
  in and does not change.

## Approaches considered

**A — `mt5.initialize(login, password, server, path)`**
Pass creds from env into the MetaTrader5 Python lib; it launches + logs in.
Smallest code change (Python only). Risk: on a fresh volume MT5 often cannot
find the broker server (empty `servers.dat`) and fails first-connect; also
conflicts with the pre-launched terminal at `04-install-mt5.sh:25`.

**B — MT5 native startup-config ini** (`terminal64.exe /config:start.ini`) — chosen primary
Write a `start.ini` from env before launch (`[Common] Login/Password/Server`,
`[Experts] AllowLiveTrading=1`), launch the terminal with it, shred the ini
after startup. Python side unchanged. This is MetaQuotes' documented headless
auto-login; it resolves the server by name on startup, so it tolerates an empty
`servers.dat` better than A, and it enables AutoTrading in the same file.
B-specific risk: some recent MT5 builds restrict plaintext `Password=` auto-login
in the startup ini (may require the password to be pre-saved, or honour it only
for demo). The cold-boot test must confirm B actually logs in on this build, not
just that it launches.

**C — VNC GUI scripting** (xdotool / AutoIt) — documented fallback only
Automate the login dialog. Mirrors the manual flow but is brittle (coordinates,
timing, focus, MT5 UI changes) and high-maintenance. Only pursued if both A and
B fail the cold-boot test.

**Decision:** implement A and B behind a mode switch, cold-boot test both, ship
the consistent winner as default. Document C as fallback; do not build it unless
needed.

## Design

### Environment variables (gateway)

| Var | Meaning | Default |
|---|---|---|
| `MT5_LOGIN` | broker account number | unset |
| `MT5_PASSWORD` | master (trading) password — plain env, matching the existing VNC `PASSWORD` convention | unset |
| `MT5_SERVER` | broker server name, e.g. `Exness-MT5Trial9` | unset |
| `MT5_AUTOLOGIN` | `b` (startup-ini) \| `a` (python-initialize) \| `off` | `b` |

`app/config.py` gains these four. When `MT5_LOGIN` is unset, behaviour is exactly
today's regardless of `MT5_AUTOLOGIN`.

### Mode B (primary)

In the startup path, when creds are present and mode is `b`:

1. Render `start.ini` (Windows-1252, CRLF) into a temp path under the Wine
   prefix:
   ```ini
   [Common]
   Login=<MT5_LOGIN>
   Password=<MT5_PASSWORD>
   Server=<MT5_SERVER>
   [Experts]
   AllowLiveTrading=1
   Enabled=1
   ```
2. Launch `wine "$mt5file" "/config:C:\\path\\start.ini" &` instead of the bare
   launch at `04-install-mt5.sh:25`.
3. After a short delay (terminal has read the file), **shred** `start.ini` so no
   plaintext password lingers in the volume.
4. Python side is unchanged: bare `mt5.initialize()` attaches to the
   now-logged-in terminal.

### Mode A (comparison)

- Do **not** pre-launch the terminal at `04-install-mt5.sh:25` (gate it off when
  mode is `a`), otherwise `initialize(login=…)` conflicts with a running
  terminal.
- `MT5Connection.initialize()` calls
  `mt5.initialize(path=<terminal64>, login=int(MT5_LOGIN), password=MT5_PASSWORD,
  server=MT5_SERVER, timeout=60000)` when creds are present and mode is `a`.

### Fallback chain (non-negotiable)

`creds present and mode≠off` → attempt env-login (A or B). On failure **or** when
creds are absent → fall back to bare `mt5.initialize()` (persisted volume). The
gateway never crashes on login failure; health stays `not_ready` (503) so qkt
waits, exactly as today. `off` is byte-for-byte current behaviour.

This means the 10 live gateways (which have a working `accounts.dat`) keep
running unchanged; they opt into env-login only when creds are supplied.

### AutoTrading ("algobot on")

Mode B sets `[Experts] AllowLiveTrading=1`. Acceptance for both modes:
`GET /account` returns `trade_allowed=true` **and** `trade_expert=true` (the
flags a live gateway reports today). If mode A leaves the terminal's algo toggle
off, enable it via the seeded terminal config; verify via `/account`.

### Central risk: empty `servers.dat` on cold boot

Both A and B can fail the first connect if MT5 does not know the broker server.
Mitigation, in order:

1. Rely on B's startup-config to resolve the server by name (MT5 pulls the
   broker's server list on startup). The cold-boot test measures whether this is
   sufficient on a truly empty volume.
2. If not sufficient: seed `servers.dat` (+ the broker `.srv`) once by copying
   from any existing working volume, baked into the image or mounted at boot.

This is the make-or-break unknown the test exists to answer.

## Test plan (real container, real broker demo — no mocks)

Requires a throwaway broker demo account (login/password/server). A fresh Exness
demo is free and instant.

**Local (first):**
1. On this branch, `docker compose build`.
2. `.env` = demo creds + `MT5_AUTOLOGIN=b`.
3. Wipe the `./config` bind (cold boot), `docker compose up`.
4. Poll `/health/ready` and `/account`. PASS = `status:ready`, `login` matches,
   `trade_allowed && trade_expert`.
5. Repeat 3 cold boots per mode (`b`, then `a`). Record success rate,
   time-to-ready, and whether `servers.dat` seeding was needed.

**Server (confirm the winner):**
- `docker run` a throwaway gateway on a spare port (e.g. 5099) with a fresh
  `mt5-test-config` volume and the winning mode; confirm `/account`; then remove
  the container and volume. **Never touch the 10 live gateways.**

**"Consistent" = ≥3/3 cold boots, both environments.**

## Rollout

1. Ship the winner into `elitekaycy/mt5-gateway-api`, default `MT5_AUTOLOGIN=b`,
   creds optional (absent → today's behaviour).
2. The dead `MT5_LOGIN/PASSWORD/SERVER` in qkt's root `docker-compose.yml`
   become live. Add them to `qkt-prod/compose.yml` + `.env.example` and the
   `templates/mt5` scaffolding so new deploys are env-login by default.
3. Existing gateways migrate when chosen; no forced cutover.

## Files touched (gateway repo)

- `scripts/04-install-mt5.sh` (+ optional `scripts/07-autologin.sh`) — render +
  shred `start.ini`, gated launch.
- `app/mt5_connection.py` — mode-A `initialize()` + fallback chain.
- `app/config.py` — the four new env vars.
- `.env.example`, `README.md`, `docs/headless-login.md` (incl. the A-vs-B
  results table).
- `scripts/test-coldboot.sh` — automate wipe → up → poll → assert.

## Error handling

- Login failure → clear log line, fall back to bare initialize, health stays 503.
- `start.ini` shredded even on failure (no plaintext password left behind).
- Mode A bounded by the existing reconnect loop (`MT5_RECONNECT_ATTEMPTS`,
  exponential backoff).

## Resolved questions

- **Secret handling:** plain `MT5_PASSWORD` env, matching the gateway's existing
  plain `PASSWORD` (VNC). Shredded from `start.ini` post-boot. No secret-store
  plumbing (YAGNI).
- **Spec home:** this file, in the gateway repo, where the code lives.

## References

- Current behaviour: `app/mt5_connection.py:76-114`, `app/app.py:56-58`,
  `scripts/04-install-mt5.sh:25`, `app/config.py`.
- Downstream dead wiring: qkt `docker-compose.yml` (`MT5_LOGIN/PASSWORD/SERVER`),
  qkt `docs/get-started/deploy-mt5.md`.
- Live evidence: `qkt-mt5` `/account` → Exness-MT5Trial9, `trade_allowed` &
  `trade_expert` true, ~14d uptime off the persisted volume with no creds in env.
