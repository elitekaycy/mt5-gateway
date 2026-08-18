# Using with qkt

[qkt](https://github.com/elitekaycy/qkt) is an event-driven trading engine
that treats this gateway as its MT5 broker backend — qkt never talks to MT5
directly, it talks to mt5-gateway's HTTP API. This page covers the
gateway side of that pairing; qkt's side is documented in
[qkt's Deploy on Exness (MT5) how-to](https://elitekaycy.github.io/qkt/how-to/deploy-exness/).

## The relationship

- **`mt5-gateway`** — this project. Wine + MT5 terminal, exposes the HTTP
  API on `:5001`.
- **`qkt`** — the trading daemon. Waits for the gateway to report
  `/health/ready` before starting, then places orders and reads market data
  through the gateway's REST API instead of an in-process MT5 SDK.

## Wiring them together

Run both as services in the same Compose project (or the same Docker
network) so qkt can reach the gateway by service name:

```yaml
services:
  mt5-gateway:
    image: elitekaycy/mt5-gateway-api:0.3.10
    restart: unless-stopped
    environment:
      MT5_LOGIN: ${MT5_LOGIN}
      MT5_PASSWORD: ${MT5_PASSWORD}
      MT5_SERVER: ${MT5_SERVER}
      API_KEY: ${API_KEY}
    volumes:
      - mt5-gateway-config:/config
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

  qkt:
    image: elitekaycy/qkt:latest
    depends_on:
      mt5-gateway:
        condition: service_healthy
    environment:
      QKT_BROKER_EXNESS_GATEWAY_URL: http://mt5-gateway:5001

volumes:
  mt5-gateway-config:
```

qkt's broker config then points `gateway_url` at that same address:

```yaml
brokers:
  exness:
    type: mt5
    gateway_url: ${QKT_BROKER_EXNESS_GATEWAY_URL}
```

qkt waits for the gateway's healthcheck (`service_healthy`, backed by
`/health/ready`) before it starts trading — the same signal the
[Quickstart](../get-started/quickstart.md) uses to confirm the gateway is
up.

## Multiple brokers

Each broker account needs its **own** gateway container — they don't share
a Wine prefix or an MT5 session. Give each one a distinct service name and
point:

```yaml
brokers:
  icmarkets:
    type: mt5
    gateway_url: http://icmarkets-gateway:5001
  ftmo:
    type: mt5
    gateway_url: http://ftmo-gateway:5001
```

Then reference each in a qkt strategy by its broker name, e.g.
`eur = ICMARKETS:EURUSD EVERY 5m`. Add each gateway to `docker-compose.yml`
with the same shape as `mt5-gateway` above — different `MT5_LOGIN` /
`MT5_SERVER`, different container/service name.

## Troubleshooting

If qkt reports the broker as unreachable, check the gateway directly first:

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/health/ready
```

A `503`/non-`connected` `mt5_status` means the gateway itself hasn't
authorized yet — see
[Install MT5 + mt5-gateway on a terminal](../get-started/install-mt5-terminal.md)
for what a healthy boot looks like and how to read its logs. VNC on `:3000`
remains available as a manual-login fallback either way.

## See also

- [qkt on GitHub](https://github.com/elitekaycy/qkt)
- [qkt's Deploy on Exness (MT5) how-to](https://elitekaycy.github.io/qkt/how-to/deploy-exness/)
- [Configuration](../reference/configuration.md) for every gateway-side env var
