# Changelog

All notable changes follow Keep a Changelog and Semantic Versioning.

## [Unreleased]

### Fixed

- `promote-to-main` no longer hangs waiting for checks on the promote PR. That
  PR is opened with `GITHUB_TOKEN`, so GitHub never runs workflows on it; the
  0.3.15 and 0.3.16 promotions both had to be finished by hand. The workflow
  now waits for `check` to pass on the exact dev commit it promotes (instead of
  trusting the latest run on dev), requires the promote tree to equal that
  commit's, and merges with `--match-head-commit`.

## [0.3.16] - 2026-09-24

### Fixed

- The derived broker UTC offset could latch a wrong value from a stale quote: a
  quote frozen for close to a whole number of hours (a stalled feed) rounded
  cleanly to an offset. On a UTC server a network drop produced `-3600`, which
  labelled every bar an hour ahead for up to six hours. Only a quote whose tick
  advanced between two reads may now derive the offset, at refresh and on GTD
  orders.
- A derived value that disagrees with the cached offset replaces it only after
  `MT5_TIME_OFFSET_CONFIRMATIONS` live readings in a row (default 2); a single
  bad reading can no longer move it.
- GTD orders use the cached offset and derive from their own symbol only when no
  usable offset exists (`MT5_TIME_ORDER_DERIVE_ATTEMPTS`,
  `MT5_TIME_ORDER_DERIVE_DELAY`).

## [0.3.15] - 2026-09-16

### Fixed

- GTD expiries on brokers without a plain `EURUSD` symbol (suffixed names such
  as `EURUSDm`, crypto-only accounts): the broker UTC offset is now derived from
  the freshest visible Market Watch quote at connect and from each GTD order's
  own symbol, instead of a hard-coded reference symbol. Previously every GTD
  order on such accounts was refused with "broker UTC offset unknown" (#93).
- The derived offset is refreshed every `MT5_TIME_REFRESH_SECONDS` (default
  10 min) while connected, so a DST switch or a market closed at boot no longer
  leaves it wrong or missing for the life of the connection. A derived value
  older than `MT5_TIME_MAX_OFFSET_AGE_SECONDS` is not used for GTD conversion.

### Added

- `MT5_SERVER_TIME_ZONE` (IANA zone) as a DST-correct explicit override.
- `GET /health` reports `server_time`: the offset in force, its source, the
  symbol it came from, when it was derived and its age.

### Removed

- Dead `Settings.server_utc_offset_seconds` (defaulted to 0 and was unused).

### Build

- The MT5-installer layer logs each attempt's exit status, tells `timeout`'s 124
  apart from a crash, and prints free space before the install and again on
  failure. A failed install previously surfaced only as a bare
  `test -f terminal64.exe`, which made a starved build disk look like a Wine
  bug (#96). Note the installer exits non-zero even on a good install, so the
  terminal check still decides success.

## [0.3.12] - 2026-08-18

### Added

- README: VHS-recorded terminal demo GIF (Docker Hub quickstart, headless
  login, health checks) with CTA badges, matching qkt's README layout.
  `docs/assets/mt5-gateway-demo.tape` is committed so it's regenerable.

### Changed

- Docs site: switched to a single dark (slate) palette, and rebuilt the
  homepage as a real landing page (hero, ticker strip, embedded terminal
  demo, 3-step walkthrough, feature grid) instead of a plain doc page.

## [0.3.11] - 2026-08-18

### Added

- mkdocs-material documentation site (`docs.yml`), deployed to GitHub Pages
  on push to `main`. Covers get-started, concepts, connecting mt5-gateway to
  qkt, a full core/optional configuration reference, and operations.
- `check.yml`'s `test`/`docker-build` jobs now skip (report success) on PRs
  that touch only docs/markdown, via a `dorny/paths-filter` gate.

### Fixed

- README: corrected two stale published-image version pins, and the
  Configuration table's missing optional env vars (now covered in full on
  the docs site).

## [0.3.10] - 2026-08-12

### Changed

- Reduced steady-state MT5 read request cost by trusting a verified connection
  for `MT5_CONNECTION_VERIFY_TTL_SECONDS` (default 30s) and relying on
  serialized IPC failure detection to mark the session disconnected immediately.
- Cached successful `symbol_select(symbol, True)` results, keeping hot read
  endpoints from re-selecting the same symbol on every request while still
  evicting cached symbols when tick/info calls return `None`.

### Fixed

- Release flow: publish the image exactly once per release — tag pushes no
  longer trigger a second build that raced the first and overwrote the shared
  Hub tags with a different digest; the `v`-prefixed tag now ships from the
  same build.
- `promote-to-main` works with branch protection again: it promotes through a
  PR (dev + merge of main), waits for checks, squash-merges, tags the release,
  and dispatches the image build, instead of a fast-forward push GitHub
  rejects.

## [0.3.9] - 2026-08-12

### Fixed

- Bumped the kclient npm overrides `brace-expansion` 1.1.17 → 1.1.18
  (CVE-2026-69152) and `socket.io-parser` 4.2.6 → 4.2.7 (CVE-2026-69185),
  which Trivy flagged as HIGH on the 0.3.8 release candidate and blocked the
  image publish.

## [0.3.8] - 2026-08-11

### Fixed

- Baked the MT5 terminal into the image at build time (pinned, checksum-verified
  stub installer run under a virtual display with a timeout+retry watchdog), so
  a cold boot no longer runs the flaky GUI installer — the volume seeds the
  terminal with the same fast copy as Mono/Python, and a MetaQuotes stub
  rotation now fails the build loudly instead of every fresh-volume boot.
- Updated the stale `mt5setup.exe` stub checksum (MetaQuotes had rotated it;
  every fresh-volume boot failed checksum verification).
- Kept `MT5_SETUP_URL` broker-branded installs working over the baked terminal:
  the branded install replaces the generic one once and is recorded, so later
  boots keep it.
- CI build time: PR and release builds now reuse the heavy Wine/MT5 layers via
  the GitHub Actions cache; release builds bust only the MT5 layer
  (`MT5_LAYER_REV`) so each published image bakes the freshest terminal.

## [0.3.5] - 2026-07-14

### Fixed

- Truncated the order comment to 25 characters in the shared trade-request
  builder, so long client comments no longer fail the native pre-trade check
  with `(-2, 'Invalid "comment" argument')`; brokers keep at most a ~16-char
  prefix and client identity travels in `client_order_id`.

## [0.3.4] - 2026-07-14

### Fixed

- Required a new MT5 authorization journal entry for each headless login attempt,
  preventing retained success lines from deleting `start.ini` before a cold terminal
  has loaded it.

## [0.3.3] - 2026-07-13

### Fixed

- Passed order check and send request fields to the MT5 native bridge positionally
  so Wine Python accepts the calls.

## [0.3.2] - 2026-07-05

### Added

- Added `MT5_ENABLE_ALGO_TRADING`, defaulting on, so headless login enables
  expert/live trading unless explicitly disabled by environment.
- Allowed Swagger UI/spec/static routes to load when `API_KEY` is enabled; actual
  API operations still require `Authorization: Bearer <key>`.
- Expanded Docker run/deploy documentation for production headless use,
  API authentication, Swagger, resolver options, and image-size tradeoffs.

## [0.3.1] - 2026-07-05

### Fixed

- Upgraded Wine Python packaging tools during image build so the release
  candidate no longer ships vulnerable `setuptools` metadata.

## [0.3.0] - 2026-07-03

### Added

- Institutional trading controls: idempotency, reconciliation, kill switch,
  API authentication, metrics, pre-trade limits, and append-only audit records.
- Headless broker resolution and login workflow.

### Fixed

- MT5 IPC serialization, retcode semantics, stop preservation, GTD mutation,
  partial-close reporting, deal aggregation, timestamps, and bounded requests.

## [0.2.0] - 2026-07-03

### Added

- Deal and tick history range endpoints.

## [0.1.0] - 2026-07-03

### Added

- Good-till-date pending-order expiration.
