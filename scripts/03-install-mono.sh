#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "03-install-mono.sh"

# Seed a fresh volume from the baked template prefix (Mono + Python + MT5 libs), so
# the display-less installs below are a fast copy instead of a ~10min re-install.
# Only when the volume lacks them; MT5 itself is still installed at runtime.
wine_template="${WINE_TEMPLATE:-/opt/wine-template}"
if [ -d "$wine_template" ] && [ ! -e "/config/.wine/drive_c/windows/mono" ]; then
    log_message "INFO" "Seeding wineprefix from baked template..."
    mkdir -p /config/.wine
    cp -a "$wine_template/." /config/.wine/
    chown -R abc:abc /config/.wine 2>/dev/null || true
    log_message "INFO" "Wineprefix seeded ($(du -sh /config/.wine 2>/dev/null | cut -f1))."
fi

# Install Mono if not present
if [ ! -e "/config/.wine/drive_c/windows/mono" ]; then
    log_message "INFO" "Downloading and installing Mono..."
    wget -O /tmp/mono.msi https://dl.winehq.org/wine/wine-mono/8.0.0/wine-mono-8.0.0-x86.msi > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        WINEDLLOVERRIDES=mscoree=d wine msiexec /i /tmp/mono.msi /qn
        if [ $? -eq 0 ]; then
            log_message "INFO" "Mono installed successfully."
        else
            log_message "ERROR" "Failed to install Mono."
        fi
        rm -f /tmp/mono.msi
    else
        log_message "ERROR" "Failed to download Mono installer."
    fi
else
    log_message "INFO" "Mono is already installed."
fi
