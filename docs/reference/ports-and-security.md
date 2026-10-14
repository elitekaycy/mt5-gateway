# Ports & security

## Ports

- **5001** — HTTP API (`MT5_API_PORT` changes the port inside the container).
  Loopback-bound by default in the repository's Compose file; set `API_KEY` before
  exposing it any further.
- **3000** — VNC desktop for optional manual login / diagnostics.

## API key

Set `API_KEY` and send it as `Authorization: Bearer <key>`. Swagger UI and
its OpenAPI spec are intentionally loadable without a key so browser docs
work, but executing any API operation still requires the bearer token. Only
`GET /health/live` is exempt from authentication besides the Swagger assets, so
`/health`, `/health/ready` and `/metrics` need the key. A missing or wrong key gets
`401` with `error_type: authentication_error`.

If `API_KEY` is unset, authentication is **disabled** and the gateway logs a warning
at start. Always set it.

## CORS

Disabled unless `CORS_ORIGINS` is explicitly configured — see
[Configuration](configuration.md). Leave it unset unless a browser-based
client needs to call the API directly.

## Network exposure

Compose binds both the API and VNC ports to loopback by default. Never
expose either port directly to the public internet; put a private network
and an authenticated reverse proxy or mTLS in front of them instead. See
[SECURITY.md](https://github.com/elitekaycy/mt5-gateway/blob/main/SECURITY.md)
for the full policy and how to report a vulnerability.
