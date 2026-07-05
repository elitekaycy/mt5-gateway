# Headless broker login

Set broker credentials in `.env` and the gateway logs into MT5 on boot — no VNC,
any broker, just the broker's **server name**. You do not need the broker's IP or a
pre-built broker directory.

| Var | Meaning |
|---|---|
| `MT5_LOGIN` | broker account number |
| `MT5_PASSWORD` | master (trading) password |
| `MT5_SERVER` | broker server **name**, e.g. `Exness-MT5Trial9`, `ICMarketsSC-Demo` |
| `MT5_ENABLE_ALGO_TRADING` | optional; defaults to `1`. Set `0`, `false`, `no`, `off`, or `disabled` to launch headless with MT5 Expert/live trading disabled. |

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

e.g. `MT5_SERVER=Exness-MT5Trial9` → resolver returns an access-point
`host:port` → MT5 authorises on `Exness-MT5Trial9`, AutoTrading on unless
`MT5_ENABLE_ALGO_TRADING=0`.

## Resolution cascade

Addresses come from three sources, tried in order, with automatic fallthrough — the
boot tries each candidate address until MT5 authorises, so a stale entry or an
unknown broker falls through on its own:

1. **Baked table** — `app/broker_servers.json`, a `name → [host:port]` map shipped
   in the image (see [harvesting](#refreshing-the-baked-table)). Offline, instant,
   no network. Covers the popular brokers.
2. **Resolver services** — `GET /Search?company=<keyword>` against `MT5_RESOLVER_URL`
   (default: public `mt5.mtapi.io`, then the optional self-hosted sidecar). These
   mirror MetaQuotes' live directory, so they cover every real MT5 broker.
3. **The server name** itself — last resort, against a baked/persisted `servers.dat`.

So the image runs as a **single container** out of the box (baked table + mtapi.io).
Resolution happens at most once per broker (its first boot); after that MT5 has
self-seeded the directory and no lookup is made.

For a **zero-third-party** setup, start the bundled self-hosted resolver and make it
the only one:

```bash
docker compose --profile self-hosted-resolver up
# and set MT5_RESOLVER_URL=http://mt5-resolver:80 to drop mtapi.io
```

### Refreshing the baked table

`scripts/harvest-broker-servers.py` regenerates `app/broker_servers.json` from the
public directory. Run it occasionally (broker addresses change rarely, and MT5
self-seeds the current directory on first connect, so a slightly stale table still
bootstraps a login), then rebuild the image.

## Tuning knobs (all optional)

| Var | Default | Meaning |
|---|---|---|
| `MT5_SERVER_ADDR` | unset | Explicit `host:port` — skip resolution and connect here directly. |
| `MT5_ENABLE_ALGO_TRADING` | `1` | Enables MT5 Expert/live trading in the startup ini. Set `0`, `false`, `no`, `off`, or `disabled` to opt out. |
| `MT5_RESOLVER_URL` | `https://mt5.mtapi.io,http://mt5-resolver:80` | Comma-separated resolver base URLs, tried in order (after the baked table). |
| `MT5_AUTORESOLVE` | `1` | `0` disables the network resolvers — use the baked table + name only. |
| `MT5_SETUP_URL` | generic MT5 | A broker-branded installer URL (e.g. `.../exness5setup.exe`) to install instead of the generic terminal. Its bundled directory also resolves the broker by name. |
| `MT5_SETUP_ATTEMPTS` / `MT5_SETUP_TIMEOUT` | `3` / `600` | Install watchdog: bound each silent-install attempt (seconds) and retry, so a stuck Wine installer can't hang the boot forever. |

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
