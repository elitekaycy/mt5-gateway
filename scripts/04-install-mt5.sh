#!/bin/bash
set -euo pipefail

source /scripts/02-common.sh

log_message "RUNNING" "04-install-mt5.sh"

# A broker-branded installer (MT5_SETUP_URL) lands in a broker-named directory
# (e.g. "MetaTrader 5 EXNESS"), not "MetaTrader 5", so locate the terminal by
# search rather than a fixed path.
program_files="/config/.wine/drive_c/Program Files"
find_terminal() {
    find "$program_files" -iname terminal64.exe -print -quit 2>/dev/null
}

installer_url="${MT5_SETUP_URL:-$mt5setup_url}"
installer_sha256="${MT5_SETUP_SHA256:-$mt5setup_sha256}"
if [ -n "${MT5_SETUP_URL:-}" ] && [ -z "${MT5_SETUP_SHA256:-}" ]; then
    log_message "ERROR" "MT5_SETUP_SHA256 is required with a custom MT5_SETUP_URL."
    exit 1
fi

if [ -n "$(find_terminal)" ]; then
    log_message "INFO" "MetaTrader 5 already installed at $(find_terminal)."
else
    log_message "INFO" "MetaTrader 5 not installed. Installing from $installer_url..."
    "$wine_executable" reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
    # The silent installer can spin forever under Wine (no terminal64.exe ever
    # written), so bound each attempt with a timeout and retry instead of hanging
    # the boot indefinitely.
    install_attempts="${MT5_SETUP_ATTEMPTS:-3}"
    install_timeout="${MT5_SETUP_TIMEOUT:-600}"
    attempt=0
    while [ "$attempt" -lt "$install_attempts" ]; do
        attempt=$((attempt + 1))
        log_message "INFO" "Downloading MT5 installer (attempt $attempt/$install_attempts)..."
        wget -O /tmp/mt5setup.exe "$installer_url" > /dev/null 2>&1
        verify_download /tmp/mt5setup.exe "$installer_sha256" || {
            log_message "ERROR" "MT5 installer checksum mismatch."
            exit 1
        }
        log_message "INFO" "Installing MetaTrader 5 (timeout ${install_timeout}s)..."
        if ! timeout "$install_timeout" "$wine_executable" /tmp/mt5setup.exe /auto; then
            log_message "WARN" "MT5 installer timed out or failed on attempt $attempt."
        fi
        rm -f /tmp/mt5setup.exe
        [ -n "$(find_terminal)" ] && break
        log_message "WARN" "Install attempt $attempt produced no terminal64.exe; retrying."
        wineserver -k 2>/dev/null || true
    done
fi

mt5exe="$(find_terminal)"
if [ -z "$mt5exe" ]; then
    log_message "ERROR" "MetaTrader 5 install failed. MT5 cannot be run."
    exit 1
fi

mt5cfg="$(dirname "$mt5exe")/Config"
sdat="$mt5cfg/servers.dat"
ini_lin="/config/.wine/drive_c/start.ini"

if [ -n "${MT5_LOGIN:-}" ]; then
    # Headless env login. Seed the baked broker directory into the volume as a
    # fallback for name-based login (major brokers, or when MT5_AUTORESOLVE=0 or
    # the resolver is unreachable). The primary path resolves the server name to an
    # address below and needs no directory — wine-in-docker can't discover brokers.
    mkdir -p "$mt5cfg"
    if [ -s /defaults/servers.dat ]; then
        # Operator-provided (baked into image, or a runtime mount) — authoritative.
        cp /defaults/servers.dat "$sdat"
        chown abc:abc "$sdat" 2>/dev/null || true
        log_message "INFO" "Seeded servers.dat from /defaults ($(wc -c < "$sdat") bytes)."
    else
        # Opt-in fetch from a private artifacts repo. Only when the volume lacks a
        # real directory (the MT5 install writes a tiny default), and only if a
        # token is set — so the public image stays clean and the open VNC /
        # user-supplied-servers.dat path is unaffected when no token is given.
        # Writes straight into the volume, so later boots don't refetch.
        cur=$([ -f "$sdat" ] && wc -c < "$sdat" || echo 0)
        if [ "$cur" -lt 100000 ] && [ -n "${QKT_ARTIFACTS_TOKEN:-}" ]; then
            repo="${QKT_ARTIFACTS_REPO:-elitekaycy/qkt-artifacts}"
            path="${QKT_ARTIFACTS_FILE:-servers.dat}"
            log_message "INFO" "Fetching servers.dat from private artifacts repo $repo."
            if curl -fsSL -H "Authorization: Bearer ${QKT_ARTIFACTS_TOKEN}" \
                    -H "Accept: application/vnd.github.raw" \
                    "https://api.github.com/repos/${repo}/contents/${path}" -o "$sdat"; then
                chown abc:abc "$sdat" 2>/dev/null || true
                log_message "INFO" "Fetched servers.dat ($(wc -c < "$sdat") bytes)."
            else
                log_message "WARN" "servers.dat fetch failed; login may not resolve the broker."
            fi
        fi
    fi
    # Build the ordered connect-candidate list — baked table, then resolver
    # services, then the server name — and try each until MT5 authorizes, so a
    # stale address or an unknown broker falls through automatically. Runs in the
    # background so the dependency install below proceeds in parallel; the terminal
    # is killed by name (not wineserver -k) between tries so it doesn't disturb it.
    jlogs="$(dirname "$mt5exe")/logs"
    python3 -c "import sys, os; sys.path.insert(0, '/app'); \
from broker_resolver import connect_candidates; \
print(chr(10).join(connect_candidates(os.environ)))" > /tmp/mt5_candidates 2>/dev/null

    render_ini() {
        MT5_SERVER="$1" python3 -c "import sys, os; sys.path.insert(0, '/app'); \
from autologin import load_settings, render_start_ini; \
open('$ini_lin', 'w', newline='').write(render_start_ini(load_settings(os.environ)))"
    }
    authorization_count() {
        python3 -c "import sys; from pathlib import Path; sys.path.insert(0, '/app'); \
from autologin import authorization_count; \
print(authorization_count(Path(sys.argv[1])))" "$jlogs"
    }
    authorized() {
        [ "$(authorization_count)" -gt "$1" ]
    }
    first_candidate="$(head -n1 /tmp/mt5_candidates 2>/dev/null)"

    (
        login_ok=0; first=1
        while IFS= read -r candidate; do
            [ -z "$candidate" ] && continue
            log_message "INFO" "Login attempt via '$candidate'."
            render_ini "$candidate"
            authorization_baseline="$(authorization_count)"
            "$wine_executable" "$mt5exe" "/config:C:\\start.ini" &
            # The first attempt gets a longer window: the terminal cold-starts and
            # compiles before it can even attempt a login.
            tries=$([ "$first" -eq 1 ] && echo 36 || echo 18); first=0
            for _ in $(seq 1 "$tries"); do
                authorized "$authorization_baseline" && { login_ok=1; break; }
                sleep 5
            done
            [ "$login_ok" -eq 1 ] && { log_message "INFO" "Authorized via '$candidate'."; break; }
            log_message "WARN" "No authorization via '$candidate'; trying next candidate."
            pkill -f terminal64.exe 2>/dev/null || true
            sleep 3
        done < /tmp/mt5_candidates
        rm -f /tmp/mt5_candidates
        # If nothing authorized, leave the terminal running on the first candidate so
        # it keeps retrying and flask can attach if the broker comes back.
        if [ "$login_ok" -ne 1 ] && [ -n "$first_candidate" ]; then
            log_message "WARN" "No candidate authorized; leaving terminal retrying."
            render_ini "$first_candidate"
            "$wine_executable" "$mt5exe" "/config:C:\\start.ini" &
        fi
        # Shred the ini — no plaintext password lingers in the volume.
        sleep 5; shred -u "$ini_lin" 2>/dev/null || rm -f "$ini_lin"
    ) &
else
    # No env login: attach to whatever the persisted volume is logged into.
    log_message "INFO" "Launching MT5 (no env-login; using persisted login if any)."
    "$wine_executable" "$mt5exe" &
fi
