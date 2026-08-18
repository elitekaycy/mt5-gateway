# mt5-gateway

A REST API for **MetaTrader 5**, running headless under Wine on Linux in Docker.

Trade, stream prices, and read account state over plain HTTP — no Windows, no
desktop, no manual login. Point it at any MetaQuotes broker with three env
vars and it logs itself in on boot.

!!! warning
    This software can place real trades against real broker accounts. Test
    with a demo account first. It is provided without warranty; see the
    [LICENSE](https://github.com/elitekaycy/mt5-gateway/blob/main/LICENSE).

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:5001/account
# {"ok": true, "login": 12345678, "server": "Exness-MT5Trial9",
#  "balance": 10000.0, "trade_allowed": true, "trade_expert": true, ...}
```

## Where to start

- New to the gateway? Start with [Quickstart](get-started/quickstart.md).
- Setting it up on a fresh terminal for the first time? See
  [Install MT5 + mt5-gateway on a terminal](get-started/install-mt5-terminal.md).
- Wiring it up as a broker for [qkt](https://github.com/elitekaycy/qkt)? See
  [Using with qkt](connect/qkt.md).
- Looking for a specific environment variable? See
  [Configuration](reference/configuration.md).

Built on the foundation laid by [slowfound](https://github.com/slowfound) in
[metatrader5-quant-server-python](https://github.com/slowfound/metatrader5-quant-server-python)
and his [tutorial series](https://youtube.com/playlist?list=PLotEOI0Sz3OzdSp7qR6vHs8EYnmQwqWAF).
