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
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account
# {"ok": true, "login": 12345678, "server": "Exness-MT5Trial9",
#  "balance": 10000.0, "trade_allowed": true, "trade_expert": true, ...}
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

## Quick start with Docker Hub

Pull the published image:

```bash
docker pull elitekaycy/mt5-gateway-api:latest
# or pin a release:
docker pull elitekaycy/mt5-gateway-api:0.3.2
```

Run headless against a broker account:

```bash
docker volume create mt5-gateway-config

docker run -d --name mt5-gateway \
  --restart unless-stopped \
  -p 127.0.0.1:5001:5001 \
  -p 127.0.0.1:3000:3000 \
  -v mt5-gateway-config:/config \
  -e MT5_LOGIN=12345678 \
  -e MT5_PASSWORD='your-trading-password' \
  -e MT5_SERVER=Exness-MT5Trial9 \
  -e MT5_ENABLE_ALGO_TRADING=1 \
  -e API_KEY='change-this-long-random-token' \
  elitekaycy/mt5-gateway-api:latest
```

Confirm the container is alive, logged in, and ready:

```bash
export API_KEY='change-this-long-random-token'

curl http://localhost:5001/health/live
# {"ok": true, "status": "alive"}

curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/health/ready
# {"ok": true, "status": "ready", "mt5_status": "connected"}

curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account
# expect your login/server plus "trade_allowed": true and "trade_expert": true
```

Swagger/OpenAPI UI is available at:

```text
http://localhost:5001/apidocs
```

If `API_KEY` is set, use Swagger's `Authorize` button with:

```text
Bearer change-this-long-random-token
```

## Quick start with Compose

```bash
cp .env.example .env      # then edit it (see below)
docker compose up -d
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account
```

Minimal `.env` for headless login to any broker:

```dotenv
MT5_LOGIN=12345678
MT5_PASSWORD=your-trading-password
MT5_SERVER=Exness-MT5Trial9      # the server name from your broker, that's all
MT5_ENABLE_ALGO_TRADING=1        # default: 1; set 0 to disable Expert/live trading
API_KEY=change-this-long-random-token
```

That's it — one container, no VNC. On first boot MT5 installs, resolves the server
name to an address, logs in with AutoTrading enabled by default, and the API comes
up on `http://localhost:5001`. Leave `MT5_LOGIN` empty to instead log in by hand
via the VNC desktop on `http://localhost:3000` (kept for diagnostics either way).

## How headless login works

1. You give the broker **server name** (e.g. `ICMarketsSC-Demo`).
2. The gateway resolves it to a trade-server **access point** (`host:port`) using a
   broker-directory search that mirrors MetaQuotes' own directory.
3. It writes MT5's startup config with `Server=<host:port>` and launches the
   terminal, which connects directly and authorizes — no broker directory needed.
4. Unless `MT5_ENABLE_ALGO_TRADING=0`, the generated startup config also enables
   MT5 Expert/live trading (`AllowLiveTrading=1`, `Enabled=1`, `Account=1`).
5. MT5 then writes its own `servers.dat` entry, so every later boot is instant and
   offline. The login is **idempotent**.

Resolution uses the public `mt5.mtapi.io` directory by default (one call, only on a
broker's first boot). For a **zero-third-party** setup, run the bundled self-hosted
resolver:

```bash
docker compose --profile self-hosted-resolver up
```

Full details and every knob: **[docs/headless-login.md](docs/headless-login.md)**.

## Production Compose example

Use a named volume, bind ports to loopback, and put the API behind a private
network or authenticated reverse proxy:

```yaml
services:
  mt5:
    image: elitekaycy/mt5-gateway-api:0.3.2
    restart: unless-stopped
    env_file: .env
    environment:
      MT5_LOGIN: ${MT5_LOGIN}
      MT5_PASSWORD: ${MT5_PASSWORD}
      MT5_SERVER: ${MT5_SERVER}
      MT5_ENABLE_ALGO_TRADING: ${MT5_ENABLE_ALGO_TRADING:-1}
      API_KEY: ${API_KEY}
      MT5_RESOLVER_URL: ${MT5_RESOLVER_URL:-https://mt5.mtapi.io,http://mt5-resolver:80}
    volumes:
      - mt5-gateway-config:/config
    ports:
      - "127.0.0.1:5001:5001"
      - "127.0.0.1:3000:3000"
    healthcheck:
      test:
        [
          "CMD-SHELL",
          'curl -fsS -H "Authorization: Bearer $$API_KEY" http://localhost:5001/health/ready',
        ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 90s

  mt5-resolver:
    image: elitekaycy/mt5-rest:latest
    profiles: ["self-hosted-resolver"]
    restart: unless-stopped

volumes:
  mt5-gateway-config:
```

For a no-third-party resolver path, start the sidecar and make it the only
resolver:

```bash
MT5_RESOLVER_URL=http://mt5-resolver:80 docker compose --profile self-hosted-resolver up -d
```

The resolver container is not the trading gateway. It only maps broker server names
to MT5 access-point addresses during first boot.

## Configuration

| Var | Meaning |
|---|---|
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | Broker account number, trading password, server name. Set these for headless login; leave empty for the manual VNC flow. |
| `MT5_ENABLE_ALGO_TRADING` | `1` by default. Set `0`, `false`, `no`, `off`, or `disabled` to launch headless with MT5 Expert/live trading disabled. |
| `MT5_SERVER_ADDR` | Explicit `host:port` to skip name resolution. |
| `MT5_AUTORESOLVE` | `0` to disable resolution (name-only login against a baked directory). |
| `MT5_RESOLVER_URL` | Comma-separated resolver URLs, tried in order. |
| `MT5_SETUP_URL` / `MT5_SETUP_SHA256` | Broker-branded installer URL and its required checksum. |
| `API_KEY` | Optional bearer token required by API operations except `/health/live`; Swagger UI/spec assets remain readable so the UI can load. |
| `CUSTOM_USER` / `PASSWORD` | VNC desktop credentials. |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

## Ports

- **5001** — HTTP API (loopback-bound by default; set `API_KEY`).
- **3000** — VNC desktop for optional manual login / diagnostics.

## Image size and production profile

The current `0.3.2`/`latest` image is intentionally self-contained: MT5 runs under
Wine, and the Wine prefix includes Windows Python plus the MetaTrader5 Python
package so a fresh volume boots quickly. On the current published `0.3.1` image,
the audit showed:

| Area | Approx size | Why it exists |
|---|---:|---|
| Docker Hub compressed layers | 2.75 GB | Network pull size for amd64 image layers. |
| Local Docker image | 7.78 GB | Expanded image plus Docker layer accounting. |
| `/opt/wine-template` | 2.0 GB | Preseeded Wine/Windows Python/MT5 Python deps; avoids slow first boot. |
| `/opt/wine-stable` | 1.5 GB | Wine runtime required to run MT5. |
| KasmVNC/base desktop stack | ~2.1 GB layer | Browser VNC desktop for diagnostics/manual login. |
| App code | <1 MB | Flask API and broker resolver are not the size driver. |

Operationally, this is not a runtime correctness problem, but it does affect image
pull time, registry bandwidth, and disk footprint. The leanest production image
would split the profiles:

- `latest` / version tag: API-first production image with Wine + virtual display,
  no browser VNC desktop.
- `dev` / diagnostic tag: current KasmVNC desktop image for manual login and
  troubleshooting.

That split is feasible, but it requires a separately validated startup path because
the current image relies on the linuxserver KasmVNC base init system. Until that
split is shipped, `latest` is the full headless-capable image with diagnostic VNC
still present. Keep ports bound to loopback or private networks in production.

## API

Interactive docs at `http://localhost:5001/apidocs` once running.

```bash
# Account
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account
# {"ok": true, "login": 12345678, "server": "Exness-MT5Trial9",
#  "balance": 10000.0, "equity": 10000.0, "trade_allowed": true,
#  "trade_expert": true, ...}

# Symbols
curl -H "Authorization: Bearer $API_KEY" "http://localhost:5001/symbols?search=*EUR*"
# {"ok": true, "total": 12, "symbols": ["EURUSD", "EURUSDm", ...]}

# Latest tick
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/symbol_info_tick/EURUSD
# {"ok": true, "bid": 1.08501, "ask": 1.08503, "time": 1783267200, ...}

# 100 M1 bars of EURUSD
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:5001/fetch_data_pos?symbol=EURUSD&timeframe=M1&num_bars=100"

# Bar range
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:5001/fetch_data_range?symbol=EURUSD&timeframe=M1&start=2026-07-01T00:00:00Z&end=2026-07-01T01:00:00Z"

# Market order: sends a real broker order
curl -X POST http://localhost:5001/order \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Idempotency-Key: strategy-a-20260703-0001" \
  -d '{
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": "BUY"
  }'
# {"ok": true, "message": "Order placed successfully", "result": {...}}

# Open positions and reconciliation
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/get_positions
curl -H "Authorization: Bearer $API_KEY" "http://localhost:5001/reconcile?magic=12345"

# Kill switch
curl -X POST -H "Authorization: Bearer $API_KEY" http://localhost:5001/kill
curl -X POST -H "Authorization: Bearer $API_KEY" http://localhost:5001/kill/release
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

Set `API_KEY` and send it as `Authorization: Bearer <key>`. Swagger UI and its
OpenAPI spec are intentionally loadable so browser docs work, but executing API
operations still requires the bearer token. CORS is disabled unless
`CORS_ORIGINS` is explicitly configured, and Compose binds API/VNC ports to
loopback. Never expose either port directly to the public internet; use a private
network and an authenticated reverse proxy or mTLS. See
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
