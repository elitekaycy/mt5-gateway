#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "04-install-mt5.sh"

# Check if MetaTrader 5 is installed
if [ -e "$mt5file" ]; then
    log_message "INFO" "File $mt5file already exists."
else
    log_message "INFO" "File $mt5file is not installed. Installing..."

    # Set Windows 10 mode in Wine and download and install MT5
    $wine_executable reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
    log_message "INFO" "Downloading MT5 installer..."
    wget -O /tmp/mt5setup.exe $mt5setup_url > /dev/null 2>&1
    log_message "INFO" "Installing MetaTrader 5..."
    $wine_executable /tmp/mt5setup.exe /auto
    rm -f /tmp/mt5setup.exe
fi

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