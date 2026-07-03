#!/bin/bash
set -euo pipefail

source /scripts/02-common.sh

log_message "RUNNING" "03-install-mono.sh"

# Install Mono if not present
if [ ! -e "/config/.wine/drive_c/windows/mono" ]; then
    log_message "INFO" "Downloading and installing Mono..."
    if wget -O /tmp/mono.msi https://dl.winehq.org/wine/wine-mono/8.0.0/wine-mono-8.0.0-x86.msi > /dev/null 2>&1; then
        verify_download /tmp/mono.msi "$mono_sha256" || {
            log_message "ERROR" "Mono installer checksum mismatch."
            exit 1
        }
        if WINEDLLOVERRIDES=mscoree=d wine msiexec /i /tmp/mono.msi /qn; then
            log_message "INFO" "Mono installed successfully."
        else
            log_message "ERROR" "Failed to install Mono."
            exit 1
        fi
        rm -f /tmp/mono.msi
    else
        log_message "ERROR" "Failed to download Mono installer."
        exit 1
    fi
else
    log_message "INFO" "Mono is already installed."
fi
