# Headless broker login

Set broker credentials in `.env` and the gateway logs into MT5 on boot — no VNC,
any broker, just the broker's **server name**. You do not need the broker's IP or a
pre-built broker directory.

| Var | Meaning |
|---|---|
| `MT5_LOGIN` | broker account number |
| `MT5_PASSWORD` | master (trading) password |
| `MT5_SERVER` | broker server **name**, e.g. `Exness-MT5Trial9`, `ICMarketsSC-Demo` |

Leaving `MT5_LOGIN` empty keeps the manual VNC flow and the persisted-volume login,
unchanged.

## Why a name is enough

MT5 under Wine cannot *discover* a broker by name on a fresh volume — it needs the
broker's record (access-point address + keys) in the encrypted `servers.dat`
directory, and there is no headless way to make MT5 fill that in from a name alone.

The gateway sidesteps this: it **resolves the server name to a raw access-point
address** (`host:port`) using a broker-directory search service, then hands MT5
`Server=<host:port>` in its startup config. MT5 connects to the access point
directly, authorises, and writes the `servers.dat` record itself. So after the first
login the volume is self-seeded and later boots are instant — the login is
idempotent.

e.g. `MT5_SERVER=Exness-MT5Trial9` → resolver returns `96.0.46.31:443` (one of the
broker's access points) → MT5 authorises on `Exness-MT5Trial9`, AutoTrading on.

## The resolver

Resolution queries a broker-directory search — `GET /Search?company=<keyword>`,
returning each matching broker's servers and their access-point `host:port` lists,
mirroring MetaQuotes' own directory. By default the gateway uses the public
`mt5.mtapi.io`, so it runs as a **single container** with nothing else to deploy.
Resolution happens at most once per broker (a non-baked broker's first boot); after
that the volume is self-seeded and no call is made.

For a **zero-third-party** setup, start the bundled self-hosted resolver:

```bash
docker compose --profile self-hosted-resolver up
```

No env change is needed — the default `MT5_RESOLVER_URL`
(`http://mt5-resolver:80,https://mt5.mtapi.io`) prefers the sidecar and falls back
to `mt5.mtapi.io` when it isn't running.

## Tuning knobs (all optional)

| Var | Default | Meaning |
|---|---|---|
| `MT5_SERVER_ADDR` | unset | Explicit `host:port` — skip resolution and connect here directly. |
| `MT5_RESOLVER_URL` | `http://mt5-resolver:80,https://mt5.mtapi.io` | Comma-separated resolver base URLs, tried in order. |
| `MT5_AUTORESOLVE` | `1` | `0` disables resolution — log in by name against a baked/persisted `servers.dat` only (majors). |
| `MT5_SETUP_URL` | generic MT5 | A broker-branded installer URL (e.g. `.../exness5setup.exe`) to install instead of the generic terminal. Its bundled directory also resolves the broker by name. |
| `MT5_SETUP_ATTEMPTS` / `MT5_SETUP_TIMEOUT` | `3` / `600` | Install watchdog: bound each silent-install attempt (seconds) and retry, so a stuck Wine installer can't hang the boot forever. |

## Login resolution order

1. `MT5_SERVER_ADDR` if set — connect there, no resolution.
2. Resolve `MT5_SERVER` → access-point `host:port` — the universal path, any broker.
3. `MT5_SERVER` name unchanged — used when the resolver is unreachable or
   `MT5_AUTORESOLVE=0`; relies on a baked/persisted `servers.dat` (major brokers).

## servers.dat (broker directory)

Still baked into the image (~728 KB, major brokers) as an offline fallback for
name-based login, but it is **no longer required** for headless login — the resolver
covers brokers it doesn't list, and MT5 self-seeds the directory on first connect.

Override without rebuilding: mount your own at `/defaults/servers.dat`, or set
`QKT_ARTIFACTS_TOKEN` to fetch it from a private repo on first boot.

## Verify

```bash
curl -s http://localhost:5001/account | python3 -m json.tool
# expect: "login": <yours>, "server": "<your server name>",
#         "trade_allowed": true, "trade_expert": true
```

## Acceptance test

```bash
MT5_LOGIN=.. MT5_PASSWORD=.. MT5_SERVER=Exness-MT5Trial9 \
  ./scripts/test-coldboot.sh 3
# expect: RESULT: 3/3 passed
```
