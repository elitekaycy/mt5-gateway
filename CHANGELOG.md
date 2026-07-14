# Changelog

All notable changes follow Keep a Changelog and Semantic Versioning.

## [Unreleased]

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
