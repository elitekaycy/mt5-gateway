# MT5 Gateway

HTTP API for MetaTrader 5 running in Wine on Linux.

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
  -d '{
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": "BUY"
  }'
```

## Credits

Built on the foundation laid by [slowfound](https://github.com/slowfound) in the [metatrader5-quant-server-python](https://github.com/slowfound/metatrader5-quant-server-python) project.
