# Sourced by mt5-gateway-demo.tape to record the README/quickstart walkthrough.
#
# The commands typed in the recording are real, copy-pasteable from the docs.
# What runs underneath is stubbed: booting a real MT5 terminal under Wine takes
# minutes and needs a live broker account, neither of which fits a short demo
# GIF. These functions print the same example output already documented in
# README.md and docs/get-started/quickstart.md, so the recording stays
# reproducible and doesn't depend on Docker Hub or a broker being reachable.

docker() {
  case "$1" in
    pull)
      cat <<'EOF'
latest: Pulling from elitekaycy/mt5-gateway-api
a1b2c3d4e5f6: Pull complete
b2c3d4e5f6a7: Pull complete
c3d4e5f6a7b8: Pull complete
Digest: sha256:9f8e7d6c5b4a392817069f4e3d2c1b0a9f8e7d6c5b4a392817069f4e3d2c1b0
Status: Downloaded newer image for elitekaycy/mt5-gateway-api:latest
docker.io/elitekaycy/mt5-gateway-api:latest
EOF
      ;;
    volume)
      echo "mt5-gateway-config"
      ;;
    run)
      echo "c1a2b3c4d5e60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9"
      ;;
    *)
      command docker "$@"
      ;;
  esac
}

curl() {
  local url="${@: -1}"
  case "$url" in
    *health/live*)
      echo '{"ok": true, "status": "alive"}'
      ;;
    *health/ready*)
      sleep 1
      echo '{"ok": true, "status": "ready", "mt5_status": "connected"}'
      ;;
    *account*)
      cat <<'EOF'
{"ok": true, "login": 12345678, "server": "Exness-MT5Trial9",
 "balance": 10000.0, "trade_allowed": true, "trade_expert": true, ...}
EOF
      ;;
    *)
      command curl "$@"
      ;;
  esac
}
