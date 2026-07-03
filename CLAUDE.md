# MT5 Gateway Engineering Constitution

## Safety invariants

- Never retry an ambiguous trade outcome without idempotency and reconciliation.
- Preserve existing SL/TP and GTD values unless removal/change is explicit.
- Use broker truth for position symbol, type, volume, orders, and fills.
- Use `Decimal` normalization for money values; reject NaN/Infinity.
- Take limits from `symbol_info`; every order sets `magic`.
- Classify MT5 retcodes only in `app/retcodes.py`; unknown means ambiguous.

## Runtime

MetaTrader5 is a process-global, single-IPC client. Every `mt5.*` call goes
through `app/mt5_connection.py`; run one process/account per container. Read
`last_error()` immediately at the serialized boundary. Reconcile after reconnect.
Broker-time conversion lives only in `app/time_utils.py`. See the
[official Python integration documentation](https://www.mql5.com/en/docs/python_metatrader5).

## Security and observability

Never log credentials or authorization headers. Mutations pass authentication,
kill-switch, pre-trade, audit, and retcode controls. Keep audit records
append-only. Public-internet exposure is unsupported.

## Code and tests

Use Ruff, mypy, pytest, Google-style docstrings, and public-function type hints.
Keep pure logic separate from the MT5 adapter. Money logic needs property tests.
Shell uses `set -euo pipefail`, quoted variables, and checksum-verified downloads.

## Workflow

Branch from `dev`; spec non-trivial behavior in `docs/specs`; write tests before
pure implementation; update Swagger/docs; cold-boot execution changes on a demo
account; PR to `dev`; promote to `main` only through the workflow. Use
Conventional Commits with subjects no longer than 72 characters.

## Prohibitions

Do not run multiple Flask processes, log secrets, add state-mutating endpoints
outside the safety gates, edit generated broker directories by hand, or bake
account-specific state into images.

See `.claude/skills/committing/SKILL.md` and
`.claude/skills/feature-development/SKILL.md`.
