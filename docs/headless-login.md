# Headless broker login

Set broker credentials in `.env` and the gateway logs into MT5 on boot — no VNC.

| Var | Meaning |
|---|---|
| `MT5_LOGIN` | broker account number |
| `MT5_PASSWORD` | master (trading) password |
| `MT5_SERVER` | broker server, e.g. `Exness-MT5Trial9` |

Leaving `MT5_LOGIN` empty keeps the manual VNC flow and the persisted-volume
login, unchanged.

## How it works

1. On boot, if `MT5_LOGIN` is set, the script seeds `servers.dat` (the broker
   directory — wine-in-docker can't discover brokers, so it's bundled) into a
   fresh `/config`.
2. It writes a startup-config ini (`[Common] Login/Password/Server`,
   `[Experts] AllowLiveTrading=1`) and launches `terminal64.exe /config:`.
3. The terminal authorizes headlessly with AutoTrading on; the ini is shredded;
   flask attaches via bare `initialize()`.

On any login failure the gateway falls back to attaching to the persisted volume,
logs the error, and reports `/health/ready` 503 until connected.

## servers.dat

`servers.dat` is MetaQuotes proprietary data — not committed. Provide it before
build (see [`defaults/README.md`](../defaults/README.md)). The ~728 KB default
directory covers the major brokers; refresh once per exotic broker.

## Verify

```bash
curl -s http://localhost:5001/account | python3 -m json.tool
# expect: "login": <yours>, "trade_allowed": true, "trade_expert": true
```

## Acceptance test

```bash
MT5_LOGIN=.. MT5_PASSWORD=.. MT5_SERVER=Exness-MT5Trial9 \
  ./scripts/test-coldboot.sh 3
# expect: RESULT: 3/3 passed
```
