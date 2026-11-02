# MT5 attestation

`promote-to-main` refuses to run unless both images are attested for the exact code being
promoted. Unit tests stub MetaTrader5, so this is what proves the gateway against a real
terminal and a real broker.

## Run it

You need Docker, and a demo account in an env file with `MT5_LOGIN`, `MT5_PASSWORD` and
`MT5_SERVER`. It refuses to trade on anything but a demo account. Pass a symbol that is
trading right now; the default `BTCUSDm` trades at weekends on Exness.

```bash
docker build -f Dockerfile.headless -t mt5-gateway:headless .
docker build -f Dockerfile -t mt5-gateway:vnc .
attestation/run.py --image mt5-gateway:headless --variant headless --env-file demo.env --record
attestation/run.py --image mt5-gateway:vnc --variant vnc --env-file demo.env --record
```

Each run takes about 40 minutes, including 12 minutes at the end watching for late fills. A full pass writes a record to `attestation/records/`.
Commit both records on the branch going to `dev`. Records hold the results, the broker
server name and the image id, and no credentials or account number.

`attestation/verify.py` checks the records. It hashes `Dockerfile`, `Dockerfile.headless`,
`app/`, `defaults/`, `root/`, `root-headless/` and `scripts/`, so any change to those needs
a new run. Docs, tests and a version bump do not.

## When to run it

It runs on a machine with Docker and a demo account, not in CI, so broker credentials stay
off GitHub. CI only checks the committed records. Use a login nothing else is trading on,
because the cases count positions and restart logins.

Run it for any change to the hashed paths above, and again when bumping the terminal, Wine or
the base image.

## What it covers

| Area | Cases |
|---|---|
| Login | Empty volume with no `servers.dat` and only server, user and password, on 5 boots. Baked table alone, resolver service alone, name-only login. Repeated restarts soon after login. Network cut during login, algo trading off, wrong password |
| Trading | Market buy and sell, SL/TP set and modified, partial close, close all by magic, all pending types with modify, cancel and expiry, idempotent replays, invalid orders |
| API | Every route, checked against `attestation/cases.py` by a unit test, so a new route fails CI until it has a case. Concurrent orders and reads |
| Security | API key, kill switch, no password left in logs or on the volume |
| Recovery | Restart, terminal crash, API crash (headless), network loss with an open position, graceful stop |
| Terminal | The running build still matches the baked build after every login and order |
| Late fills | The whole account ends flat after a watch. Late fills are closed and counted in the record |

## What it does not cover

- **Asynchronous fills.** Dealer-desk brokers acknowledge an order with price 0 and fill it
  later. A demo account that fills synchronously never takes that path, so it stays covered
  by unit tests.
- **Other brokers and real accounts.** A pass shows the gateway working with this broker's
  demo server.
- **The future.** MetaQuotes and brokers change things outside this repo. Run this again
  when bumping the terminal, Wine or the base image.

A record proves the code at one point in time. Treat a failure on unchanged code as news
from the outside world, such as a new MT5 build or a broker change.
