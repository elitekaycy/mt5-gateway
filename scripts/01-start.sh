#!/bin/bash
set -euo pipefail

# Source common variables and functions
source /scripts/02-common.sh

# Run installation scripts
/scripts/03-install-mono.sh
/scripts/04-install-mt5.sh
/scripts/05-install-python.sh
/scripts/06-install-libraries.sh

# Start Flask API with waitress
log_message "INFO" "Starting Flask API with waitress..."
cd /app
exec wine python -m waitress --call --host=0.0.0.0 --port="${MT5_API_PORT:-5001}" --threads=4 app:create_app
