#!/bin/bash
set -euo pipefail

source /scripts/02-common.sh

log_message "RUNNING" "06-install-libraries.sh"

# Install Python dependencies in Wine. Skipped when the volume was seeded from the
# baked template (the libs are already present) — checked via the core MT5 package.
if "$wine_executable" python -c "import MetaTrader5" > /dev/null 2>&1; then
    log_message "INFO" "Python dependencies already present (seeded); skipping install."
else
    log_message "INFO" "Installing Python dependencies in Windows"
    "$wine_executable" python -m pip install --no-cache-dir -r /app/requirements.txt
fi
