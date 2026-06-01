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

## servers.dat (broker directory)

`servers.dat` is MetaQuotes proprietary data — not committed, and (for a public
image) not baked. Headless login needs it so the terminal can resolve the broker
(wine-in-docker can't discover brokers). Provide it any of three ways:

1. **Runtime mount** — `-v /path/servers.dat:/defaults/servers.dat:ro`. The boot
   copies it into the MT5 config. Keeps the image clean.
2. **Private artifacts fetch** — set `QKT_ARTIFACTS_TOKEN` (read-only PAT); the
   gateway pulls `servers.dat` from `QKT_ARTIFACTS_REPO` on first boot and
   persists it to the volume. Opt-in: empty token skips it, so the public image
   and the open path are unaffected.
3. **Build bake** — drop `defaults/servers.dat` before `docker build` (only for a
   *private* image; a public image would expose it).

Without any of these, leave `MT5_LOGIN` empty and use the one-time VNC login,
which caches `servers.dat` in the volume itself. The ~728 KB directory covers the
major brokers; refresh once per exotic broker.

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
