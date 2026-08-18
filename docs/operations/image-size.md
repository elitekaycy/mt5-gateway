# Image size & profiles

The published image is intentionally self-contained: MT5 runs under Wine,
and the Wine prefix includes Windows Python, the MetaTrader5 Python package,
and the MT5 terminal itself, so a fresh volume boots quickly.

On the published `0.3.1` image, an audit showed the following breakdown.
The image has moved to `0.3.10` since, and this hasn't been re-measured —
treat these as indicative, not exact, until someone re-runs the audit
against the current tag.

| Area | Approx size | Why it exists |
|---|---:|---|
| Docker Hub compressed layers | 2.75 GB | Network pull size for amd64 image layers. |
| Local Docker image | 7.78 GB | Expanded image plus Docker layer accounting. |
| `/opt/wine-template` | 2.0 GB | Preseeded Wine prefix with Windows Python, MT5 Python deps, and the MT5 terminal itself; a cold boot never runs an installer. |
| `/opt/wine-stable` | 1.5 GB | Wine runtime required to run MT5. |
| KasmVNC/base desktop stack | ~2.1 GB layer | Browser VNC desktop for diagnostics/manual login. |
| App code | <1 MB | Flask API and broker resolver are not the size driver. |

Operationally, this is not a runtime correctness problem, but it does affect
image pull time, registry bandwidth, and disk footprint. The leanest
production image would split the profiles:

- `latest` / version tag: API-first production image with Wine + virtual
  display, no browser VNC desktop.
- `dev` / diagnostic tag: current KasmVNC desktop image for manual login and
  troubleshooting.

That split is feasible, but it requires a separately validated startup path
because the current image relies on the linuxserver KasmVNC base init
system. Until that split is shipped, `latest` is the full headless-capable
image with diagnostic VNC still present. Keep ports bound to loopback or
private networks in production — see [Ports & security](../reference/ports-and-security.md).
