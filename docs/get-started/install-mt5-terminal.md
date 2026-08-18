# Install MT5 + mt5-gateway on a terminal

This is what happens when you run the container with `MT5_LOGIN` set — no
desktop, no VNC, nothing to click. Useful if you want to understand the boot
sequence, debug a stuck login, or run this on a headless server.

## 1. The terminal is already installed

The published image bakes the MT5 terminal, Windows Python, and the
`MetaTrader5` Python package into a preseeded Wine prefix
(`/opt/wine-template`). A fresh `mt5-gateway-config` volume boots by seeding
from that template — no installer runs. `scripts/04-install-mt5.sh` only
falls back to a live install if the volume somehow has no `terminal64.exe`
(a volume from before MT5 was baked in) or if you set a custom
`MT5_SETUP_URL` for a broker-branded installer.

## 2. The gateway resolves your broker's server name to an address

MT5 under Wine can't discover a broker by name on a fresh volume — that
requires an encrypted `servers.dat` directory MT5 normally downloads itself,
and there's no headless way to trigger that download. Instead, `broker_resolver.py`
turns your `MT5_SERVER` name (e.g. `Exness-MT5Trial9`) into a raw
`host:port` access point, trying in order:

1. A baked table (`app/broker_servers.json`) shipped in the image — instant,
   offline, covers popular brokers.
2. Resolver services (`MT5_RESOLVER_URL`, default `mt5.mtapi.io`, optionally
   a self-hosted sidecar) — mirror MetaQuotes' own live directory, covering
   any real MT5 broker.
3. The server name itself, against whatever `servers.dat` is already on the
   volume — a last-resort fallback for major brokers.

Every source's candidates are combined into one ordered, de-duplicated list.

## 3. The terminal launches and tries each candidate until one authorizes

For each candidate address, the boot script writes an MT5 startup config
(`start.ini`) with `Server=<host:port>` and your credentials, launches
`terminal64.exe /config:C:\start.ini`, and watches the terminal's own log
files for an `"Authorized on"` line. The first candidate gets a longer
window (terminal cold-start + compile); later ones get less. If a candidate
doesn't authorize within its window, the terminal is killed by name and the
next candidate is tried.

```ini
[Common]
Login=12345678
Password=your-trading-password
Server=Exness-MT5Trial9

[Experts]
AllowLiveTrading=1
Enabled=1
Account=1
```

The `[Experts]` block is what `MT5_ENABLE_ALGO_TRADING` controls — set it to
`0` to boot with Expert/live trading disabled.

## 4. Once authorized, the login becomes self-sufficient

The MT5 terminal writes its own `servers.dat` entry for the server it just
connected to. Every later boot of that same volume finds the broker in its
own directory and skips resolution entirely — instant, offline restarts.
This is why the login is described as idempotent: repeating it is a no-op
once the volume has authorized once.

The rendered `start.ini` is shredded (`shred -u`, falling back to `rm -f`)
a few seconds after the login attempt starts, so no plaintext password
lingers in the volume.

## 5. If nothing authorizes

If every candidate fails, the boot leaves the terminal running against the
first candidate so it keeps retrying in the background — the gateway process
itself still starts, but `/health/ready` reports `mt5_status` as
disconnected until a login succeeds. Check `docker compose logs mt5-gateway`
for `"Login attempt via"` / `"No candidate authorized"` lines, and confirm
`MT5_SERVER` matches your broker's server name exactly (case-sensitive, no
typos in the trailing digits — `Exness-MT5Trial9` is not `Exness-MT5Trial`).

See [Configuration](../reference/configuration.md) for every resolver and
retry knob, and [How headless login works](../headless-login.md) for the
full reference doc this walkthrough summarizes.
