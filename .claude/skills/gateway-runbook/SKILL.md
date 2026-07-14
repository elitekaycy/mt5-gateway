---
name: gateway-runbook
description: Use when working in the mt5-gateway repository beyond a routine commit — new modules or endpoints, execution-path changes, debugging live behavior, releases, or environment/bootstrap work. The system map and operational runbook that complements CLAUDE.md (constitution) and the committing/feature-development checklists.
---

# gateway-runbook — system map and operations

Flask REST gateway fronting a real MetaTrader 5 terminal under Wine/Mono,
one process per account. Python 3.9, Ruff + mypy strict + pytest/Hypothesis,
coverage ≥80. `CLAUDE.md` holds the safety constitution; the two mini-skills
(`committing`, `feature-development`) hold the checklists; this skill holds
the map and the runbook.

## 1. Map — where behavior lives

- `app/mt5_connection.py` — the ONLY seam to `mt5.*`. MetaTrader5 is a
  process-global, single-IPC, non-thread-safe client: every call serializes
  through here, and `mt5.last_error()` is read immediately at this boundary
  (it's global state — a later call overwrites it).
- `app/retcodes.py` — the closed retcode taxonomy. Unknown retcode =
  ambiguous outcome = reconciliation, never retry. Classify retcodes here
  and nowhere else.
- `app/money.py` — Decimal normalization; floats stop at the MT5 boundary;
  quantize with `Decimal.quantize`, never `round()`.
- `app/time_utils.py` — the only broker-time↔UTC conversion point.
- Safety chain for mutations: `security.py` (auth) → `kill_switch.py` →
  `pretrade.py` (validation, limits from `symbol_info`) → `idempotency.py` →
  `audit.py` (append-only) → retcode classification. Every state-mutating
  route passes through all of it; a new endpoint that skips one is a P0.
- `app/autologin.py` + `app/broker_resolver.py` — headless any-broker login
  (server-name → `Server=host:port` cascade; see `docs/headless-login.md`).
  Pure logic deliberately separated from the MT5 adapter — copy this pattern
  for new modules.
- `app/routes/` — account, order, position, control, data, history, symbol,
  health. Route changes update Swagger (`app/swagger.py`) in the same PR.
- `tests/conftest.py` stubs MetaTrader5 at the module boundary — new tests
  stub there, never deeper. Money logic gets Hypothesis property tests.

## 2. Execution-path rules that bite

- **Never wrap `mt5.order_send` in a retry.** It retries internally (~10×);
  a gateway-level retry on an ambiguous outcome can double-fill. Ambiguity
  goes through `reconciliation.py` against broker truth.
- Preserve existing SL/TP/GTD on modify unless removal is explicit — a
  modify that omits them deletes them at the broker.
- Every `order_send` sets `magic`; comments are capped at 31 chars by MT5
  (longer comments are a real historical rejection cause).
- "MT5 returned None" is a mask — the actual cause is in `last_error()` at
  the serialized boundary.
- GTD expiry: the gateway historically hardcoded `ORDER_TIME_GTC`; when
  touching order time-in-force, verify the wire actually carries GTD.

## 3. Runbook

- **Bootstrap** (fresh box/container): `scripts/01-*.sh` … `06-*.sh` in
  order — Wine/Mono, MT5 terminal, Python env, libs. Checksums verified;
  `set -euo pipefail` everywhere.
- **Cold-boot verification** (REQUIRED for execution-path PRs):
  `scripts/test-coldboot.sh` against a demo account; paste the account,
  authorization, and result evidence into the PR.
- **Broker servers**: `scripts/harvest-broker-servers.py` regenerates
  `app/broker_servers.json`; `defaults/servers.dat` is captured, not
  synthesizable. Never hand-edit either; commit regenerated artifacts as
  their own commit.
- **Local gate** (identical to CI, run before any push):
  `ruff check . && ruff format --check . && mypy app/ && pytest -q --cov`.
- **Release**: branch from `dev`, PR to `dev`; promote via the
  `promote-to-main` workflow; Docker Hub `elitekaycy/mt5-gateway-api` tags
  `latest` / VERSION / `v*` / `sha-*`; the workflow asserts git tag ==
  `VERSION` file — bump `VERSION` only in a release PR.
- **Ops gotcha**: recreating the gateway container kills dependent qkt
  strategy sessions (feed budget) — restart the qkt container afterwards.

## 4. Never

- Multiple Flask processes/workers against one terminal (single IPC).
- Logging credentials, `MT5_PASSWORD`, VNC `PASSWORD`, or Authorization
  headers.
- Mutating endpoints outside the §1 safety chain.
- Hand-editing generated broker directories or baking account state into
  images.
- Committing `.env`, `config/`, captured `servers.dat`, or local deploy
  scripts (`deploy-cutedge-endpoints.sh` is gitignored for a reason).

## Living document

Fix this skill in the same PR that proves it wrong or incomplete. One source
of truth per rule: the gate command lives in CONTRIBUTING.md — if it changes
there, update `committing/SKILL.md` and this file in the same change.
