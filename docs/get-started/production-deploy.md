# Production deploy

Use a named volume, bind ports to loopback, and put the API behind a private
network or authenticated reverse proxy:

```yaml
services:
  mt5:
    image: elitekaycy/mt5-gateway-api:0.3.10
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

The resolver container is not the trading gateway. It only maps broker
server names to MT5 access-point addresses during first boot.

See [Ports & security](../reference/ports-and-security.md) before exposing
this beyond a private network.
