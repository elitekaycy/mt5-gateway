# MT5 Gateway

[![CI](https://github.com/elitekaycy/mt5-gateway/actions/workflows/check.yml/badge.svg)](https://github.com/elitekaycy/mt5-gateway/actions/workflows/check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/elitekaycy/mt5-gateway-api)](https://hub.docker.com/r/elitekaycy/mt5-gateway-api)

A REST API for **MetaTrader 5**, running headless under Wine on Linux in Docker.

Trade, stream prices, and read account state over plain HTTP — no Windows, no
desktop, no manual login. Point it at any MetaQuotes broker with three env vars and
it logs itself in on boot.

> [!WARNING]
> This software can place real trades against real broker accounts. Test with a
> demo account first. It is provided without warranty; see [LICENSE](LICENSE).

Based on [slowfound's metatrader5-quant-server-python](https://github.com/slowfound/metatrader5-quant-server-python/tree/chapter-1) and his [YouTube tutorial series](https://youtube.com/playlist?list=PLotEOI0Sz3OzdSp7qR6vHs8EYnmQwqWAF).

```bash
curl http://localhost:5001/account
# {"login": 298615298, "server": "Exness-MT5Trial9", "balance": 8483.49,
#  "trade_allowed": true, ...}
```

## Why this exists

MetaTrader 5 is a Windows GUI application with a closed protocol. Running it as a
service normally means a Windows box and a human clicking "Login." This project runs
the real MT5 terminal under Wine and exposes its Python API as a REST service, so any
language or system can drive an MT5 account programmatically.

The hard part is logging in **headless, for any broker**. MT5 can't discover a broker
by name on a fresh install without its encrypted broker directory (`servers.dat`),
and that file can't be generated. This gateway solves it: it **resolves the broker's
server name to a connectable address** and connects directly, so you supply only the
account credentials and the server *name* — never an IP, a directory file, or a VNC
session.

## Quick start

```bash
cp .env.example .env      # then edit it (see below)
docker compose up
curl http://localhost:5001/account
```

Minimal `.env` for headless login to any broker:

```dotenv
MT5_LOGIN=298615298
MT5_PASSWORD=your-trading-password
MT5_SERVER=Exness-MT5Trial9      # the server name from your broker, that's all
```

That's it — one container, no VNC. On first boot MT5 installs, resolves the server
name to an address, logs in with AutoTrading enabled, and the API comes up on
`http://localhost:5001`. Leave the `MT5_*` vars empty to instead log in by hand via
the VNC desktop on `http://localhost:3000` (kept for diagnostics either way).

## How headless login works

1. You give the broker **server name** (e.g. `ICMarketsSC-Demo`).
2. The gateway resolves it to a trade-server **access point** (`host:port`) using a
   broker-directory search that mirrors MetaQuotes' own directory.
3. It writes MT5's startup config with `Server=<host:port>` and launches the
   terminal, which connects directly and authorizes — no broker directory needed.
4. MT5 then writes its own `servers.dat` entry, so every later boot is instant and
   offline. The login is **idempotent**.

Resolution uses the public `mt5.mtapi.io` directory by default (one call, only on a
broker's first boot). For a **zero-third-party** setup, run the bundled self-hosted
resolver:

```bash
docker compose --profile self-hosted-resolver up
```

Full details and every knob: **[docs/headless-login.md](docs/headless-login.md)**.

## Configuration

| Var | Meaning |
|---|---|
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | Broker account number, trading password, server name. Set these for headless login; leave empty for the manual VNC flow. |
| `MT5_SERVER_ADDR` | Explicit `host:port` to skip name resolution. |
| `MT5_AUTORESOLVE` | `0` to disable resolution (name-only login against a baked directory). |
| `MT5_RESOLVER_URL` | Comma-separated resolver URLs, tried in order. |
| `MT5_SETUP_URL` / `MT5_SETUP_SHA256` | Broker-branded installer URL and its required checksum. |
| `API_KEY` | Optional bearer token required by every endpoint except `/health/live`. |
| `CUSTOM_USER` / `PASSWORD` | VNC desktop credentials. |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

## Ports

- **5001** — HTTP API (loopback-bound by default; set `API_KEY`).
- **3000** — VNC desktop for optional manual login / diagnostics.

## API

Interactive docs at `http://localhost:5001/apidocs` once running.

```bash
# Account
curl http://localhost:5001/account

# 100 M1 bars of EURUSD
curl "http://localhost:5001/fetch_data_pos?symbol=EURUSD&timeframe=M1&num_bars=100"

# Market order
curl -X POST http://localhost:5001/order \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: strategy-a-20260703-0001" \
  -d '{
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": "BUY"
  }'
```

Clients should send a stable `Idempotency-Key` header (or matching
`client_order_id` body field) for every intended trade. Repeating the same key and
request replays the original response without placing another order. Reusing a key
with different parameters returns `409`. A `502 unknown_outcome` means the broker
may have accepted the request; reconcile positions and order/deal history before
retrying.

When calling `/modify_sl_tp`, an omitted `sl` or `tp` preserves its current value.
Removing protection requires the explicit `clear_sl: true` or `clear_tp: true`
field.

Every JSON response includes `ok`. Collection responses use `data`; successful
mutations also include a human-readable `message`, broker `result`, and
operation-specific safety fields. Errors include `ok: false`, `error`, and
`error_type`, with optional `details`, `request_id`, and `mt5_error`.
Interactive endpoint schemas are available at `/apidocs`.

## Security posture

Set `API_KEY` and send it as `Authorization: Bearer <key>`. CORS is disabled
unless `CORS_ORIGINS` is explicitly configured, and Compose binds API/VNC ports
to loopback. Never expose either port directly to the public internet; use a
private network and an authenticated reverse proxy or mTLS. See
[SECURITY.md](SECURITY.md).

## Operations

- `/health/live` checks only process liveness.
- `/health/ready` requires a connected MT5 account and inactive kill switch.
- `/metrics` exposes Prometheus-compatible safety/connection counters.
- `POST /kill` halts trading; `POST /kill/release` resumes it.
- `GET /reconcile?magic=...` returns broker positions, orders, and recent deals.
- Set `MT5_SERVER_UTC_OFFSET_SECONDS` if the broker encodes server-local epochs.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the trading-system engineering
standards in [CLAUDE.md](CLAUDE.md).

## Architecture

```
REST client ──HTTP──▶ Flask (waitress)  ──Python IPC──▶  MT5 terminal (Wine)  ──▶ broker
                          │                                    ▲
                          └── broker_resolver: name ──▶ host:port ┘  (first boot only)
```

- `app/` — Flask routes, safety controls, MT5 connection, and broker resolver.
- `scripts/` — boot, Wine/MT5 install, resolver cascade, and headless login.
- MT5 state persists in the `/config` Docker volume.

## Development

```bash
ruff check .
mypy app/
pytest -q --cov
```

## Credits

Built on the foundation laid by [slowfound](https://github.com/slowfound) in
[metatrader5-quant-server-python](https://github.com/slowfound/metatrader5-quant-server-python)
and his [tutorial series](https://youtube.com/playlist?list=PLotEOI0Sz3OzdSp7qR6vHs8EYnmQwqWAF).

## License

MIT.
