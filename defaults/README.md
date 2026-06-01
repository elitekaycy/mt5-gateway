# defaults/servers.dat

MT5's broker directory (`servers.dat`) — required for headless env login so the
terminal can resolve the broker server (wine-in-docker can't discover brokers).

**Not committed** (MetaQuotes proprietary data). Provide it before `docker build`:

```bash
# from a gateway already logged in to your broker:
docker cp <gateway>:"/config/.wine/drive_c/Program Files/MetaTrader 5/Config/servers.dat" defaults/servers.dat
```

The ~728 KB default directory covers the major brokers (Exness, IC Markets, FTMO,
Pepperstone, …). To add an exotic broker, connect it once and re-copy the file.

Alternative to baking it into the image: mount it at runtime to
`/defaults/servers.dat` (keeps a public image free of proprietary data).
