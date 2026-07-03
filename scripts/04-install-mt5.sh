#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "04-install-mt5.sh"

# A broker-branded installer (MT5_SETUP_URL) lands in a broker-named directory
# (e.g. "MetaTrader 5 EXNESS"), not "MetaTrader 5", so locate the terminal by
# search rather than a fixed path.
program_files="/config/.wine/drive_c/Program Files"
find_terminal() { find "$program_files" -iname terminal64.exe 2>/dev/null | head -1; }

installer_url="${MT5_SETUP_URL:-$mt5setup_url}"

if [ -n "$(find_terminal)" ]; then
    log_message "INFO" "MetaTrader 5 already installed at $(find_terminal)."
else
    log_message "INFO" "MetaTrader 5 not installed. Installing from $installer_url..."
    $wine_executable reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
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
        log_message "INFO" "Installing MetaTrader 5 (timeout ${install_timeout}s)..."
        timeout "$install_timeout" $wine_executable /tmp/mt5setup.exe /auto
        rm -f /tmp/mt5setup.exe
        [ -n "$(find_terminal)" ] && break
        log_message "WARN" "Install attempt $attempt produced no terminal64.exe; retrying."
        wineserver -k 2>/dev/null || true
    done
fi

mt5exe="$(find_terminal)"
if [ -z "$mt5exe" ]; then
    log_message "ERROR" "MetaTrader 5 install failed. MT5 cannot be run."
    exit 0
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
    # Resolve the broker server NAME to a connectable access-point address, so a
    # fresh volume with no baked directory can still log in — MT5 connects by raw
    # host:port and writes the directory entry itself. Falls back to the name when
    # the resolver is unreachable or an explicit MT5_SERVER_ADDR is set.
    resolved="$(python3 -c "import sys, os; sys.path.insert(0, '/app'); \
from broker_resolver import choose_server; print(choose_server(os.environ))" 2>/dev/null)"
    if [ -n "$resolved" ]; then
        [ "$resolved" != "${MT5_SERVER:-}" ] && log_message "INFO" "Resolved '${MT5_SERVER:-}' -> '$resolved'."
        export MT5_SERVER="$resolved"
    fi
    # Render the startup-config ini (login + AllowLiveTrading) and launch with it.
    log_message "INFO" "Env-login: writing start.ini and launching terminal with /config:."
    python3 -c "import sys, os; sys.path.insert(0, '/app'); \
from autologin import load_settings, render_start_ini; \
open('$ini_lin', 'w', newline='').write(render_start_ini(load_settings(os.environ)))"
    $wine_executable "$mt5exe" "/config:C:\\start.ini" &
    # Shred the ini after the terminal has read it — no plaintext password lingers.
    ( sleep 45; shred -u "$ini_lin" 2>/dev/null || rm -f "$ini_lin" ) &
else
    # No env login: attach to whatever the persisted volume is logged into.
    log_message "INFO" "Launching MT5 (no env-login; using persisted login if any)."
    $wine_executable "$mt5exe" &
fi