# Documentation site — mkdocs + GitHub Pages

Date: 2026-08-18
Status: proposed
Scope: repo root (`mkdocs.yml`, `requirements-docs.txt`, `.github/workflows/docs.yml`), `docs/`

## Problem

mt5-gateway has no browsable documentation site. Everything lives in
`README.md` plus a handful of files under `docs/` (`headless-login.md`, specs,
plans). As the project goes open source, that's thin: there's no install
walkthrough, no complete config reference (the README's config table omits
over a dozen env vars — see Evidence below), and no discoverable home for
concepts like headless login or the safety controls.

qkt already solved this shape of problem: mkdocs-material site, deployed to
GitHub Pages on push to `main`, with a nav organized by audience (get
started → concepts → reference → operations → contributing). mt5-gateway
should get the same pipeline, scaled down to a single-service project.

### Evidence — README config table is incomplete

`app/config.py`, `app/mt5_connection.py`, `app/pretrade.py`, `app/audit.py`,
`app/kill_switch.py`, `app/request_limits.py`, and `app/swagger.py` read env
vars the README's Configuration table never mentions:

`MT5_API_PORT`, `MT5_RECONNECT_ATTEMPTS`, `MT5_RECONNECT_BASE_DELAY`,
`MT5_CONNECTION_VERIFY_TTL_SECONDS`, `MT5_TIME_DERIVE_ATTEMPTS`,
`MT5_TIME_DERIVE_DELAY`, `CORS_ORIGINS`, `MAX_NUM_BARS`,
`MAX_HISTORY_RANGE_DAYS`, `SYMBOL_WHITELIST`, `MAX_ORDER_VOLUME`,
`MAX_PRICE_DEVIATION_PCT`, `MAX_ORDER_DEVIATION`, `ORDER_AUDIT_FILE`,
`KILL_SWITCH_FILE`, `SWAGGER_SCHEME`, `CUSTOM_USER`/`PASSWORD` (VNC, listed
but undocumented as optional).

The docs site's Configuration reference is the fix: every var above gets
documented, split into **core** (required for headless login: `MT5_LOGIN`,
`MT5_PASSWORD`, `MT5_SERVER`, `API_KEY`) vs **optional** (everything else,
grouped by concern: connection tuning, pre-trade limits, request limits,
audit/kill-switch file paths, VNC, misc).

## Goals

- `mkdocs.yml` + Material theme, deployed via GitHub Actions to
  `https://elitekaycy.github.io/mt5-gateway/` on push to `main`.
- Nav scaled to a single-service project — no tutorials/examples sections
  invented to mirror qkt's shape; only what there's real content for.
- Configuration reference documents **every** env var above, core vs
  optional, with defaults and one-line meaning each.
- A "Using with qkt" page — the gateway is qkt's MT5 broker backend; anyone
  who found this repo from qkt (or vice versa) should see the connection
  documented and get a link back to qkt.
- API reference is a pointer to the live `/apidocs` Swagger UI, not a
  separately built static page (no OpenAPI-export step — nothing to keep in
  sync).

## Non-goals

- README rewrite / trading-floor visual theme — separate follow-up.
- Custom logo/brand SVGs — separate follow-up; site ships with a Material
  stock icon as logo+favicon for now.
- Static OpenAPI/Swagger export into the site.

## Design

### Files

```
mkdocs.yml
requirements-docs.txt
.github/workflows/docs.yml
docs/
  index.md
  assets/
    extra.css
  get-started/
    index.md
    quickstart.md
    install-mt5-terminal.md
    production-deploy.md
  concepts/
    index.md
    why-headless-login.md
    architecture.md
  connect/
    qkt.md
  reference/
    index.md
    configuration.md
    api.md
    ports-and-security.md
  operations/
    index.md
    health-and-safety.md
    image-size.md
  contributing.md
  headless-login.md        # existing file, kept, linked from concepts + get-started
  specs/                    # existing, excluded from nav via exclude_docs
  plans/                    # existing, excluded from nav via exclude_docs
```

`docs/specs/` and `docs/plans/` are excluded from the built site (`exclude_docs`
in `mkdocs.yml`, same mechanism qkt uses for its `superpowers/` dir) — they're
working documents, not public docs.

### mkdocs.yml

Same shape as qkt's, trimmed:

- `site_name: mt5-gateway`, `site_url: https://elitekaycy.github.io/mt5-gateway/`
- `repo_url` / `repo_name` / `edit_uri` pointed at this repo
- `theme.name: material`, palette toggle (dark slate default / light), a
  Material stock icon (e.g. `material/chart-candlestick`) as `theme.icon.logo`
  and favicon — no `custom_dir`/SVG assets yet
- `extra_css: [assets/extra.css]` — a small stylesheet nudging the palette
  toward the trading-floor tone (dark background, monospace code accents),
  not a full re-theme
- `plugins: [search, mermaid2]` — mermaid needed for the architecture diagram
- `markdown_extensions`: same admonition/tabbed/superfences/tasklist set as
  qkt (already proven to render this project's README-style callouts, e.g.
  the `> [!WARNING]` block)
- `nav`:

```yaml
nav:
  - Home: index.md
  - Get started:
      - get-started/index.md
      - Quickstart: get-started/quickstart.md
      - Install MT5 + mt5-gateway on a terminal: get-started/install-mt5-terminal.md
      - Production deploy: get-started/production-deploy.md
  - Concepts:
      - concepts/index.md
      - Why this exists: concepts/why-headless-login.md
      - How headless login works: headless-login.md
      - Architecture: concepts/architecture.md
  - Connect:
      - Using with qkt: connect/qkt.md
  - Reference:
      - reference/index.md
      - Configuration: reference/configuration.md
      - API: reference/api.md
      - Ports & security: reference/ports-and-security.md
  - Operations:
      - operations/index.md
      - Health, kill switch, reconcile, metrics: operations/health-and-safety.md
      - Image size & profiles: operations/image-size.md
  - Contributing: contributing.md
```

### Content sourcing

- **Quickstart** — the Docker Hub + Compose quick-start blocks already in
  README, moved (not duplicated — README keeps a short version + link once
  the README redesign happens later).
- **Install MT5 + mt5-gateway on a terminal** — new content: walks through
  what happens on first boot (`scripts/04-install-mt5.sh`, autologin,
  `servers.dat` generation) from a terminal-only perspective, no VNC. This is
  the piece Dickson specifically asked for.
- **Why this exists / How headless login works** — lifted from README's
  existing sections, verified against `app/broker_resolver.py` and
  `app/autologin.py` for accuracy.
- **Architecture** — README's ASCII diagram converted to a mermaid diagram
  (qkt's plugin set already supports this).
- **Connect → Using with qkt** — modeled directly on
  `qkt/docs/how-to/deploy-exness.md`: `QKT_BROKER_EXNESS_GATEWAY_URL` /
  `gateway_url` pointing at this container's `:5001`, the
  `depends_on` + healthcheck relationship (qkt waits for
  `/health/ready`), multi-broker pattern (one gateway container per broker
  account), and a link back to `qkt`
  (https://github.com/elitekaycy/qkt) and its
  [deploy-exness how-to](https://elitekaycy.github.io/qkt/how-to/deploy-exness/)
  once that page's URL is confirmed live.
- **Configuration** — full table per Evidence above, core vs optional,
  cross-checked line-by-line against `app/config.py`, `app/mt5_connection.py`,
  `app/pretrade.py`, `app/audit.py`, `app/kill_switch.py`,
  `app/request_limits.py`, `app/swagger.py`.
- **API** — short page: link to `/apidocs`, note on `Idempotency-Key`,
  response envelope shape (`ok`/`data`/`error`), pointer to
  `app/routes/` for the endpoint list.
- **Ports & security** — README's "Security posture" + "Ports" sections,
  verified against `app/security.py` and `docker-compose.yml`.
- **Operations** — README's "Operations" section, verified against
  `app/routes/control.py` (kill switch), `app/reconciliation.py`,
  `app/metrics.py`.
- **Image size & profiles** — README's existing size-audit table, carried
  over as-is (already accurate per `defaults/README.md` context) unless the
  `0.3.10` build changed the numbers — worth a quick re-check during
  implementation, not re-deriving from scratch.

### requirements-docs.txt

```
mkdocs==1.6.1
mkdocs-material==9.5.49
mkdocs-mermaid2-plugin==1.2.1
pymdown-extensions==10.21.2
pygments==2.20.0
```

Same pinned versions as qkt — known-good combination, no reason to drift.

### .github/workflows/docs.yml

Same shape as qkt's, minus the Gradle/Dokka steps (mt5-gateway has no
compiled-API-doc generator):

- Trigger: `push` to `main` with `paths` filtering on `docs/**`,
  `mkdocs.yml`, `requirements-docs.txt`, `.github/workflows/docs.yml`; plus
  `workflow_dispatch`.
- `permissions: contents: read, pages: write, id-token: write`
- `concurrency: group: docs-deploy, cancel-in-progress: true`
- Job 1 (`build`): checkout → setup Python 3.12 (pip cache keyed on
  `requirements-docs.txt`) → `pip install -r requirements-docs.txt` →
  `mkdocs build --strict` → `actions/upload-pages-artifact` with `path: site`.
- Job 2 (`deploy`): `actions/deploy-pages`, `needs: build`,
  `environment: github-pages`.

This is additive to the existing `check.yml` CI — doesn't touch release/promote
workflows referenced in CLAUDE.md's Workflow section.

## Testing / verification

- `mkdocs build --strict` locally must pass with zero warnings (broken
  internal links, missing nav entries) before this ships.
- Manually click through the built site once (`mkdocs serve`) — verify the
  Configuration table renders correctly and the Connect → qkt page's links
  resolve.
- After first deploy, confirm `https://elitekaycy.github.io/mt5-gateway/`
  is live and GitHub Pages is enabled on the repo (Settings → Pages → source:
  GitHub Actions) — this is a one-time repo setting change outside the
  workflow file itself; flag it to Dickson rather than assuming it's on.

## Open questions for implementation

- Repo Pages source needs to be set to "GitHub Actions" manually before the
  first deploy succeeds — not something the workflow file can do.
- Confirm the qkt deploy-exness page URL once qkt's own site nav is stable
  (path shown above is a best guess from `mkdocs.yml`'s nav structure).
