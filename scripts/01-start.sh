#!/bin/bash
set -euo pipefail

# Source common variables and functions
source /scripts/02-common.sh

# Run installation scripts
/scripts/03-install-mono.sh
/scripts/04-install-mt5.sh

# MT5 runs one instance. An API that initializes before the boot's terminal is up launches
# its own, with no start.ini, and that one wins: it never logs in and the boot waits out the
# whole login window. So hold the API until the terminal the boot started is running.
for _ in $(seq 1 "${MT5_TERMINAL_WAIT_SECONDS:-60}"); do
    pgrep -f '^C:\\.*terminal64\.exe' > /dev/null && break
    sleep 1
done

/scripts/05-install-python.sh
/scripts/06-install-libraries.sh

# Start Flask API with waitress
log_message "INFO" "Starting Flask API with waitress..."
cd /app
exec wine python -m waitress --call --host=0.0.0.0 --port="${MT5_API_PORT:-5001}" --threads=4 app:create_app
