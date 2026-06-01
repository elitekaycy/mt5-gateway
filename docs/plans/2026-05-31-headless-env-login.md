# Headless env-driven MT5 login — Implementation Plan (verified recipe)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A fresh gateway container logs into the broker from env vars with AutoTrading on, no VNC, consistently — using the recipe proven by the 2026-05-31 spike (mode B startup-ini + seeded `servers.dat`).

**Architecture:** Pure login *policy* (settings, ini render) lives in `app/autologin.py` (no `MetaTrader5` import → host pytest, no mocks). The *mechanism* — seed `servers.dat`, write `start.ini`, launch `terminal64 /config:`, shred — lives in the boot script and is validated by the real cold-boot harness. `mt5_connection.py` is unchanged: it already does bare `initialize()`, which attaches once the terminal is logged in. Mode A is dropped (spike showed its IPC timeout was a harness artifact; mode B works through flask).

**Tech Stack:** Python 3 (Flask/waitress under Wine), bash install scripts, Docker, MetaTrader5 package, pytest (host, dev-only).

**Spec:** `docs/specs/2026-05-31-headless-env-login-design.md` (see the "Update 2026-05-31 — verified recipe" section).

---

## File structure

**Create:**
- `app/autologin.py` — `AutoLoginSettings`, `load_settings`, `validate`, `render_start_ini`. No `MetaTrader5` import.
- `tests/test_autologin.py` — host pytest.
- `requirements-dev.txt` — `pytest`.
- `scripts/test-coldboot.sh` — wipe `./config` → up → poll → assert (mode B).
- `docs/headless-login.md` — operator doc.
- `.gitignore` entry + `defaults/README.md` — for the private `servers.dat` artifact.

**Modify:**
- `scripts/04-install-mt5.sh` — seed `servers.dat`, write/shred `start.ini`, mode-aware launch.
- `app/app.py` — call `autologin.validate` at startup, log clearly, never crash.
- `Dockerfile` — `COPY` the private `servers.dat` artifact to `/defaults/` (if present at build).
- `.env.example`, `README.md` — document the env vars.

**Unchanged:** `app/mt5_connection.py` (bare `initialize()` already correct), `app/config.py`.

**Env vars (gateway):** `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`. Login is attempted when `MT5_LOGIN` is non-empty; otherwise today's behaviour (attach to persisted volume).

---

## Task 1: Pure policy — settings + validation (TDD)

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/test_autologin.py`
- Create: `app/autologin.py`

- [ ] **Step 1: Dev dependency**

Create `requirements-dev.txt`:

```
pytest==8.3.3
```

Run: `python3 -m pip install -r requirements-dev.txt`
Expected: pytest installed/satisfied.

- [ ] **Step 2: Failing test**

Create `tests/test_autologin.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from autologin import AutoLoginSettings, load_settings, validate


def test_login_absent_means_disabled():
    s = load_settings({})
    assert s.enabled is False
    assert s.login == ""


def test_load_settings_reads_and_strips():
    s = load_settings({
        "MT5_LOGIN": " 436145944 ",
        "MT5_PASSWORD": "Angelboy1@",
        "MT5_SERVER": " Exness-MT5Trial9 ",
    })
    assert s.login == "436145944"
    assert s.server == "Exness-MT5Trial9"
    assert s.password == "Angelboy1@"
    assert s.enabled is True


def test_validate_rejects_login_without_server():
    with pytest.raises(ValueError, match="MT5_SERVER"):
        validate(AutoLoginSettings(login="1", password="p", server=""))


def test_validate_rejects_login_without_password():
    with pytest.raises(ValueError, match="MT5_PASSWORD"):
        validate(AutoLoginSettings(login="1", password="", server="s"))


def test_validate_allows_absent_creds():
    validate(load_settings({}))  # must not raise
```

- [ ] **Step 3: Run — must fail**

Run: `python3 -m pytest tests/test_autologin.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autologin'`.

- [ ] **Step 4: Implement**

Create `app/autologin.py`:

```python
"""Headless env-driven MT5 login policy.

Pure module: NO MetaTrader5 import, so it runs under host pytest. It decides
*what* to do (is login enabled, what startup ini); the boot script performs the
MT5-coupled mechanism (seed servers.dat, launch terminal with the ini).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AutoLoginSettings:
    login: str
    password: str
    server: str

    @property
    def enabled(self) -> bool:
        """True when env-login should be attempted (a login number is present)."""
        return bool(self.login)


def load_settings(env) -> AutoLoginSettings:
    """Build settings from an environ-like mapping, e.g. load_settings(os.environ)."""
    return AutoLoginSettings(
        login=env.get("MT5_LOGIN", "").strip(),
        password=env.get("MT5_PASSWORD", ""),
        server=env.get("MT5_SERVER", "").strip(),
    )


def validate(s: AutoLoginSettings) -> None:
    """Raise ValueError on an unusable config. Absent login is valid (no env-login)."""
    if s.login and not s.server:
        raise ValueError("MT5_LOGIN set but MT5_SERVER is empty")
    if s.login and not s.password:
        raise ValueError("MT5_LOGIN set but MT5_PASSWORD is empty")
```

- [ ] **Step 5: Run — must pass**

Run: `python3 -m pytest tests/test_autologin.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt tests/test_autologin.py app/autologin.py
git commit -m "feat(autologin): add settings loader and validation"
```

---

## Task 2: Startup-config ini renderer (TDD)

**Files:**
- Modify: `tests/test_autologin.py`, `app/autologin.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_autologin.py`:

```python
from autologin import render_start_ini


def test_render_start_ini_has_login_block_and_autotrading():
    s = AutoLoginSettings(login="436145944", password="pw", server="Exness-MT5Trial9")
    ini = render_start_ini(s)
    assert "[Common]" in ini
    assert "Login=436145944" in ini
    assert "Password=pw" in ini
    assert "Server=Exness-MT5Trial9" in ini
    assert "[Experts]" in ini
    assert "AllowLiveTrading=1" in ini


def test_render_start_ini_uses_crlf():
    ini = render_start_ini(AutoLoginSettings(login="1", password="p", server="s"))
    assert "\r\n" in ini and ini.endswith("\r\n")
```

- [ ] **Step 2: Run — must fail**

Run: `python3 -m pytest tests/test_autologin.py -k render -v`
Expected: FAIL — `cannot import name 'render_start_ini'`.

- [ ] **Step 3: Implement**

Append to `app/autologin.py`:

```python
def render_start_ini(s: AutoLoginSettings) -> str:
    """Render an MT5 startup-config ini that auto-logs-in and enables algo trading.

    Passed to the terminal as `terminal64.exe /config:<file>`. e.g. login 123 on
    Exness-MT5Trial9 -> "[Common]\\r\\nLogin=123\\r\\nServer=Exness-MT5Trial9...".
    Windows CRLF — MT5 parses the config as a Windows ini.
    """
    lines = [
        "[Common]",
        f"Login={s.login}",
        f"Password={s.password}",
        f"Server={s.server}",
        "",
        "[Experts]",
        "AllowLiveTrading=1",
        "Enabled=1",
        "Account=1",
    ]
    return "\r\n".join(lines) + "\r\n"
```

- [ ] **Step 4: Run — must pass**

Run: `python3 -m pytest tests/test_autologin.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/test_autologin.py app/autologin.py
git commit -m "feat(autologin): render MT5 startup-config ini"
```

---

## Task 3: Mode-aware launch + servers.dat seed in 04-install-mt5.sh

Validated by the cold-boot harness (Task 6). When `MT5_LOGIN` is set: seed `servers.dat` if the volume lacks it, write `start.ini`, launch the terminal with `/config:`, shred the ini. Otherwise keep today's bare launch.

**Files:**
- Modify: `scripts/04-install-mt5.sh` (the run block, lines ~22-28).

- [ ] **Step 1: Replace the run block**

Replace from `# Recheck if MetaTrader 5 is installed` to end of file with:

```bash
# Recheck if MetaTrader 5 is installed
if [ ! -e "$mt5file" ]; then
    log_message "ERROR" "File $mt5file is not installed. MT5 cannot be run."
    exit 0
fi

mt5cfg="/config/.wine/drive_c/Program Files/MetaTrader 5/Config"
sdat="$mt5cfg/servers.dat"
ini_lin="/config/.wine/drive_c/start.ini"

if [ -n "${MT5_LOGIN:-}" ]; then
    # Headless env login. Seed the broker directory if the volume lacks it —
    # wine-in-docker can't discover brokers, so the server can't resolve without it.
    mkdir -p "$mt5cfg"
    if [ ! -s "$sdat" ] && [ -s /defaults/servers.dat ]; then
        cp /defaults/servers.dat "$sdat"
        chown abc:abc "$sdat" 2>/dev/null || true
        log_message "INFO" "Seeded servers.dat from /defaults."
    fi
    # Render the startup-config ini (login + AllowLiveTrading) and launch with it.
    log_message "INFO" "Env-login: writing start.ini and launching terminal with /config:."
    python3 -c "import sys, os; sys.path.insert(0, '/app'); \
from autologin import load_settings, render_start_ini; \
open('$ini_lin', 'w', newline='').write(render_start_ini(load_settings(os.environ)))"
    $wine_executable "$mt5file" "/config:C:\\start.ini" &
    # Shred the ini after the terminal has read it — no plaintext password lingers.
    ( sleep 45; shred -u "$ini_lin" 2>/dev/null || rm -f "$ini_lin" ) &
else
    # No env login: attach to whatever the persisted volume is logged into.
    log_message "INFO" "Launching MT5 (no env-login; using persisted login if any)."
    $wine_executable "$mt5file" &
fi
```

- [ ] **Step 2: Lint**

Run: `bash -n scripts/04-install-mt5.sh`
Expected: no output (valid bash).

- [ ] **Step 3: Commit**

```bash
git add scripts/04-install-mt5.sh
git commit -m "feat(scripts): headless env login via startup ini + servers.dat seed"
```

---

## Task 4: Validate config at startup (clear logs, never crash)

**Files:**
- Modify: `app/app.py` (the startup block, lines ~55-58).

- [ ] **Step 1: Add validation before initialize**

Replace:

```python
conn = MT5Connection.get_instance()
if not conn.initialize():
    logger.error("Failed to initialize MT5, but starting server anyway")
```

with:

```python
import sys as _sys
_sys.path.insert(0, "/app")
from autologin import load_settings, validate
try:
    validate(load_settings(os.environ))
except ValueError as e:
    logger.error(f"Invalid env-login config: {e}")

conn = MT5Connection.get_instance()
if not conn.initialize():
    logger.error("Failed to initialize MT5, but starting server anyway")
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile app/app.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add app/app.py
git commit -m "feat(app): validate env-login config at startup"
```

---

## Task 5: servers.dat private-artifact plumbing

`servers.dat` is MetaQuotes proprietary data — never committed. Provided at build time as a gitignored artifact, COPYed to `/defaults/`. The boot script (Task 3) seeds it into a fresh volume.

**Files:**
- Modify: `.gitignore`, `Dockerfile`
- Create: `defaults/README.md`

- [ ] **Step 1: Ignore the artifact**

Append to `.gitignore` (create if absent):

```
# MetaQuotes proprietary broker directory — provide at build, never commit
defaults/servers.dat
```

- [ ] **Step 2: Document how to obtain it**

Create `defaults/README.md`:

```markdown
# defaults/servers.dat

MT5's broker directory (`servers.dat`) — required for headless env login so the
terminal can resolve the broker server (wine-in-docker can't discover brokers).

**Not committed** (MetaQuotes proprietary). Provide it before `docker build`:

    cp "<a working MT5 data dir>/Config/servers.dat" defaults/servers.dat

e.g. from a gateway already logged in to your broker:

    docker cp <gateway>:"/config/.wine/drive_c/Program Files/MetaTrader 5/Config/servers.dat" defaults/servers.dat

The ~728 KB default directory covers the major brokers (Exness, IC Markets, FTMO,
Pepperstone, …). To add an exotic broker, connect it once and re-copy the file.
```

- [ ] **Step 3: COPY it into the image (tolerant of absence)**

In `Dockerfile`, after `COPY app /app`, add:

```dockerfile
# Broker directory for headless env login (gitignored; provide before build).
# The trailing glob makes the COPY succeed even when the file is absent.
COPY app/requirements.txt defaults/servers.da[t] /defaults/
```

Note: the `defaults/servers.da[t]` glob is a Docker trick — the COPY does not fail when the file is missing, so builds without env login still work. (`app/requirements.txt` is a guaranteed-present anchor so the multi-source COPY is valid.)

- [ ] **Step 4: Build sanity (no env-login path still builds)**

Run: `docker build -t mt5-gw-test . 2>&1 | tail -5`
Expected: `naming to ... mt5-gw-test` (build succeeds with or without `defaults/servers.dat`).

- [ ] **Step 5: Commit**

```bash
git add .gitignore Dockerfile defaults/README.md
git commit -m "build: seed servers.dat from a private build artifact"
```

---

## Task 6: Cold-boot harness (mode B)

**Files:**
- Create: `scripts/test-coldboot.sh`

- [ ] **Step 1: Write it**

Create `scripts/test-coldboot.sh`:

```bash
#!/usr/bin/env bash
# Cold-boot env-login acceptance test (real container, real broker demo).
# Requires defaults/servers.dat present (broker directory) and a demo account.
#
# Usage:
#   MT5_LOGIN=.. MT5_PASSWORD=.. MT5_SERVER=Exness-MT5Trial9 \
#     ./scripts/test-coldboot.sh <iterations>
#
# PASS per boot = /health/ready 200 AND /account login matches AND
#                 trade_allowed && trade_expert both true.
set -uo pipefail

iters="${1:-3}"
: "${MT5_LOGIN:?set MT5_LOGIN}" "${MT5_PASSWORD:?set MT5_PASSWORD}" "${MT5_SERVER:?set MT5_SERVER}"
export MT5_LOGIN MT5_PASSWORD MT5_SERVER
pass=0

for i in $(seq 1 "$iters"); do
  echo "── boot $i/$iters ──"
  docker compose down -v >/dev/null 2>&1 || true
  rm -rf ./config && mkdir -p ./config
  docker compose up -d --build >/dev/null

  ready=""
  for _ in $(seq 1 120); do            # up to 10 min (install + login)
    if curl -sf http://localhost:5001/health/ready >/dev/null 2>&1; then ready=1; break; fi
    sleep 5
  done

  acct="$(curl -s http://localhost:5001/account || true)"
  read -r login te < <(printf '%s' "$acct" | python3 -c \
'import sys,json
try:
 d=json.load(sys.stdin); print(d.get("login",""), d.get("trade_allowed") and d.get("trade_expert"))
except Exception: print("", "")' 2>/dev/null)

  if [ "$ready" = "1" ] && [ "$login" = "$MT5_LOGIN" ] && [ "$te" = "True" ]; then
    echo "  PASS  login=$login autotrading=$te"
    pass=$((pass + 1))
  else
    echo "  FAIL  ready=${ready:-0} login=${login:-none} autotrading=${te:-none}"
    docker compose logs --tail 25 mt5 2>/dev/null || true
  fi
done

echo "RESULT: $pass/$iters passed"
docker compose down -v >/dev/null 2>&1 || true
[ "$pass" -eq "$iters" ]
```

- [ ] **Step 2: Make executable, lint**

Run: `chmod +x scripts/test-coldboot.sh && bash -n scripts/test-coldboot.sh`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add scripts/test-coldboot.sh
git commit -m "test(coldboot): add env-login cold-boot acceptance harness"
```

---

## Task 7: Operator docs

**Files:**
- Modify: `.env.example`, `README.md`
- Create: `docs/headless-login.md`

- [ ] **Step 1: `.env.example`**

Append to `.env.example`:

```
# ── Headless broker login (optional) ────────────────────────────────────────
# Set these and the gateway logs into the broker on boot — no VNC. Leave
# MT5_LOGIN empty to keep the manual VNC flow + persisted-volume login.
# Requires defaults/servers.dat present at build (the broker directory).
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=Exness-MT5Trial9
```

- [ ] **Step 2: `README.md`** — under the VNC-login step, add:

```markdown
   **Or skip the GUI:** set `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` in `.env`
   (and provide `defaults/servers.dat`) — the gateway logs in on boot. See
   [docs/headless-login.md](docs/headless-login.md). VNC stays for diagnostics.
```

- [ ] **Step 3: `docs/headless-login.md`**

```markdown
# Headless broker login

Set broker credentials in `.env` and the gateway logs into MT5 on boot — no VNC.

| Var | Meaning |
|---|---|
| `MT5_LOGIN` | broker account number |
| `MT5_PASSWORD` | master (trading) password |
| `MT5_SERVER` | broker server, e.g. `Exness-MT5Trial9` |

Leaving `MT5_LOGIN` empty keeps the manual VNC flow, unchanged.

## How it works

1. On boot, if `MT5_LOGIN` is set, the script seeds `servers.dat` (the broker
   directory — wine-in-docker can't discover brokers, so it's bundled) into a
   fresh `/config`.
2. It writes a startup-config ini (`[Common] Login/Password/Server`,
   `[Experts] AllowLiveTrading=1`) and launches `terminal64.exe /config:`.
3. The terminal authorizes headlessly with AutoTrading on; the ini is shredded;
   flask attaches via bare `initialize()`.

## servers.dat

`servers.dat` is MetaQuotes proprietary data — not committed. Provide it before
build (see `defaults/README.md`). The ~728 KB default directory covers the major
brokers; refresh once per exotic broker.

## Verify

    curl -s http://localhost:5001/account | python3 -m json.tool
    # expect: "login": <yours>, "trade_allowed": true, "trade_expert": true
```

- [ ] **Step 4: Commit**

```bash
git add .env.example README.md docs/headless-login.md
git commit -m "docs: document headless env login"
```

---

## Task 8: End-to-end verification + PR

- [ ] **Step 1: Provide the broker directory**

```bash
# from a gateway already logged in to the broker:
docker cp <gateway>:"/config/.wine/drive_c/Program Files/MetaTrader 5/Config/servers.dat" defaults/servers.dat
```

- [ ] **Step 2: Cold-boot test (3×, real demo)**

```bash
export MT5_LOGIN=436145944 MT5_PASSWORD='Angelboy1@' MT5_SERVER=Exness-MT5Trial9
./scripts/test-coldboot.sh 3
```
Expected: `RESULT: 3/3 passed`.

- [ ] **Step 3: Full pytest + push**

```bash
python3 -m pytest tests/ -v        # all green
git push origin feat/headless-env-login
```

- [ ] **Step 4: PR (ask elitekaycy first)**

```bash
gh pr create --base main --head feat/headless-env-login \
  --title "feat: headless env-driven MT5 login" \
  --body "Spec/plan in docs/. Fresh gateway logs into the broker from env (startup-ini + seeded servers.dat), AutoTrading on, no VNC. Verified on the prod image with an Exness demo. Backward compatible: no MT5_LOGIN -> today's persisted-volume behaviour. servers.dat seeded from a private build artifact, never committed."
```

---

## Follow-up (separate PR, qkt repos — not this repo)

Wire the now-live env vars downstream once the image ships:
- `qkt-prod/compose.yml` + `.env.example`: add `MT5_LOGIN/PASSWORD/SERVER` to the `mt5-gateway` service, and a `defaults/servers.dat` seed (build arg or mounted).
- qkt `src/main/resources/templates/mt5/`: same, so scaffolded deploys are env-login by default.
- Per broker = one gateway service (its creds) + one `brokers:` entry in `qkt.config.yaml` (its route). qkt routes by symbol prefix; it never sees the password.
