# MT5 Gateway

[![CI](https://github.com/elitekaycy/mt5-gateway/actions/workflows/check.yml/badge.svg)](https://github.com/elitekaycy/mt5-gateway/actions/workflows/check.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/elitekaycy/mt5-gateway-api)](https://hub.docker.com/r/elitekaycy/mt5-gateway-api)

HTTP API for MetaTrader 5 running in Wine on Linux.

> [!WARNING]
> This software can place real trades against real broker accounts. Test with a
> demo account first. It is provided without warranty; see [LICENSE](LICENSE).

Based on [slowfound's metatrader5-quant-server-python](https://github.com/slowfound/metatrader5-quant-server-python/tree/chapter-1) and his [YouTube tutorial series](https://youtube.com/playlist?list=PLotEOI0Sz3OzdSp7qR6vHs8EYnmQwqWAF).

## Requirements

- Docker and Docker Compose ([Install Docker](https://docs.docker.com/get-docker/))

## Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your MT5 credentials and VNC password

3. Start the server:
   ```bash
   docker compose up
   ```

4. **Important**: Connect to VNC at `localhost:3000` using your VNC password. Login to MT5 with your broker account through the GUI. The API endpoints won't work until you're logged in.

   **Or skip the GUI:** set `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` in `.env` (and provide `defaults/servers.dat`) — the gateway logs in on boot, no VNC. See [docs/headless-login.md](docs/headless-login.md). VNC stays available for diagnostics.

5. API is now available at `http://localhost:5001`

## Ports

- **3000** - VNC server for MT5 GUI access
- **5001** - HTTP API

## API Documentation

Full interactive API documentation available at `http://localhost:5001/apidocs` after starting the server.

## Example Usage

Get account info:
```bash
curl http://localhost:5001/account
```

Fetch 100 bars of data:
```bash
curl "http://localhost:5001/fetch_data_pos?symbol=EURUSD&timeframe=M1&num_bars=100"
```

Place a market order:
```bash
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

## Credits

Built on the foundation laid by [slowfound](https://github.com/slowfound) in the [metatrader5-quant-server-python](https://github.com/slowfound/metatrader5-quant-server-python) project.
