#!/bin/bash
set -euo pipefail

source /scripts/02-common.sh

log_message "RUNNING" "06-install-libraries.sh"

# Install all Python dependencies in Windows
log_message "INFO" "Installing Python dependencies in Windows"
"$wine_executable" python -m pip install --no-cache-dir -r /app/requirements.txt
