# VNC and headless image variants

## Why

The image was 8.42 GB locally (0.3.19), 3.1 GB to pull. About 1.6 GB was dead bytes in
lower layers, about 1.2 GiB was DLLs the prefix copies from Wine and never loads, and
about 2 GB was a browser desktop that production does not use.

## Design

| | `Dockerfile` (VNC) | `Dockerfile.headless` |
|---|---|---|
| Tags | `latest`, `X.Y.Z`, `vX.Y.Z`, `sha-*` (unchanged) | `headless`, `X.Y.Z-headless`, `vX.Y.Z-headless`, `sha-*-headless` |
| Base | linuxserver KasmVNC | linuxserver Debian, same s6 init and `abc` uid |
| Display | Xvnc, with the browser desktop on `:3000` | Xvfb, API on `:5001` only |
| Starts the gateway from | the openbox session | the `svc-gateway` s6 service |

Both log in from environment variables. `scripts/bake-wine-template.sh` builds one prefix
for both, so a `/config` volume moves between them in either direction.

The VNC image keeps its plain tags and its desktop, so existing deployments pull the same
names and nothing about `:3000` changes. Only the headless image is new.

## What changed in the prefix

- Wine builtin DLLs in `system32`/`syswow64` are links to Wine's own copies. Only files
  byte-identical to Wine's are linked.
- Mono is not installed. The empty `windows/mono` stays because `03-install-mono.sh`, here
  and in any older image rolled back to, reads it as "already seeded". Without it an older
  image would copy its template over a newer volume, through the links.
- Removed: MetaEditor, metatester, the MT5 uninstaller, bundled sample history, installer
  caches, and Python docs, Tcl/Tk, headers and tools.

Existing volumes are never reseeded, so they keep what they have.

## Terminal pin and start check

MT5 builds 6274, 6281 and 6295 stop under Wine 10 with a false "A debugger has been found"
dialog, on kernels 6.8 and 7.0. Build 6244 runs. Published images from at least 0.3.24 bake
an affected build, and 0.3.26 fails to log in on a fresh volume. Deployments keep working
only because their volumes hold an older terminal.

So both images copy build 6244 from the 0.3.19 image, pinned by digest, and the bake starts
the terminal and fails the build on a dialog or a missing journal. Emptying
`MT5_TERMINAL_SOURCE` returns to the installer. Do that when a build runs under the Wine in
use; the start check decides whether it does.

## Testing

`tests/test_image_variants.py` pins what must stay equal between the images and covers the
bake functions. `scripts/test-image-variant.py` boots a real image against a demo account:
login, market data, an order round trip, restart, terminal and API crashes, secrets, and
graceful stop. It refuses to trade unless the broker reports a demo account.

Run it for fresh volumes on both images, a volume moved between them, a rollback to the
previous image, and a copy of a volume from a real deployment.

## Fixes found by that testing

- `10031` is ambiguous, not retryable: deal history showed closes answered with it executing
  within 200 ms, and others not executing. qkt already treats 409 and 5xx as ambiguous.
- The boot writes the algo-trading switch to `Config/common.ini`, so a terminal relaunched
  after a crash can trade instead of rejecting orders with 10027. `Account` is now always 0:
  MT5 documents 1 as "disable when connecting with a different account", which also caught a
  first login made through the API after a boot-time outage.

## Known gap

A terminal that auto-updates to an affected build would stop on its next start.
