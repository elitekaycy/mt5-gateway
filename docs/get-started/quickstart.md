# Quickstart

Pull the published image:

```bash
docker pull elitekaycy/mt5-gateway-api:latest
# or pin a release:
docker pull elitekaycy/mt5-gateway-api:0.3.10
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

Swagger/OpenAPI UI is available at `http://localhost:5001/apidocs`. If
`API_KEY` is set, use Swagger's `Authorize` button with
`Bearer change-this-long-random-token`.

## With Docker Compose

```bash
cp .env.example .env      # then edit it — see Configuration
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

That's it — one container, no VNC. MT5 is baked into the image (no installer
ever runs at boot); on first boot the gateway seeds the volume, resolves the
server name to an address, logs in with AutoTrading enabled by default, and
the API comes up on `http://localhost:5001`. Leave `MT5_LOGIN` empty to
instead log in by hand via the VNC desktop on `http://localhost:3000` (kept
for diagnostics either way).

See [Configuration](../reference/configuration.md) for every available env
var, and [How headless login works](../headless-login.md) for what happens
under the hood.
