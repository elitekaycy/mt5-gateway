# defaults/servers.dat

MT5's broker directory — committed and baked into the image so any user logs in
headlessly with just their `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER`, no manual
setup. It carries broker server names + access-point addresses (**no
credentials**). The ~728 KB default directory covers the major brokers (Exness,
IC Markets, FTMO, Pepperstone, …).

To refresh it (e.g. add an exotic broker), pull a current copy from a logged-in
terminal and replace this file, then rebuild:

```bash
docker cp <gateway>:"/config/.wine/drive_c/Program Files/MetaTrader 5/Config/servers.dat" defaults/servers.dat
```

Override at deploy time without rebuilding: mount your own at
`/defaults/servers.dat`, or set `QKT_ARTIFACTS_TOKEN` to fetch from a private repo.
