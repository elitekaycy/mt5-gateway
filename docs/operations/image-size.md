# Image size & profiles

The gateway ships as two images. Both run the real MT5 terminal under Wine, log in from
environment variables, serve the same API and use the same `/config` volume.

| | VNC (default) | Headless |
|---|---|---|
| Tags | `latest`, `X.Y.Z` | `headless`, `X.Y.Z-headless` |
| Browser desktop on `:3000` | Yes | No |
| Manual login and troubleshooting by desktop | Yes | No |
| Size on disk | 4.43 GB | 3.32 GB |
| API restarts itself if it crashes | No | Yes |

Use headless for production unless you need the desktop. Before these images, 0.3.19 was
8.42 GB on disk.

## Moving between them

Stop the container and start the other image on the same `/config`. Moving a volume in
either direction was tested, as was going back to an earlier image. With the headless
image, set `MT5_LOGIN`, `MT5_PASSWORD` and `MT5_SERVER`, or use a volume that is already
logged in, because there is no desktop to log in from.

```bash
docker compose -f docker-compose.headless.yml up -d --build
```

## The terminal is pinned

Both images bake MT5 build 6244 instead of the newest one. Builds 6274, 6281 and 6295 stop
under Wine 10 with a false `A debugger has been found running in your system` dialog, which
nobody can see on a virtual display. The symptom is `/health/ready` staying at 503 with
`MetaTrader 5 x64 not found (-10003)` in the logs and no `logs` directory in the MT5 folder.

Published images 0.3.24 to 0.3.26 bake affected builds. They keep working on volumes that
already hold an older terminal, but fail on a fresh volume.

The build now starts the terminal and fails if it shows a dialog or writes no journal. To
try a newer build, build with an empty `MT5_TERMINAL_SOURCE` and let that check decide:

```bash
docker build -f Dockerfile.headless --build-arg MT5_TERMINAL_SOURCE= -t mt5-gateway:try .
```

Wine 11 does not help yet: build 6244 starts under it, but the installer for the newest build
hung for all three attempts.

`MT5_SETUP_URL` at runtime installs whatever build that URL serves, so it can hit this too.

## What was removed

- Duplicate DLLs: the prefix now links to Wine's copies, which also makes each new volume
  about 1.6 GiB smaller (2571 MiB to about 900 MiB).
- Dead layers: the VNC system layers are flattened, so deleted and rewritten files stop
  counting.
- Docker, compilers, Mono, MetaEditor, metatester, sample history and installer caches.

Keep ports bound to loopback or private networks in production. See
[Ports & security](../reference/ports-and-security.md).
