#!/usr/bin/env bash
# Cold-boot env-login acceptance test (real container, real broker demo).
# Requires defaults/servers.dat present (broker directory) and a demo account.
#
# Usage:
#   MT5_LOGIN=.. MT5_PASSWORD=.. MT5_SERVER=Exness-MT5Trial9 \
#     ./scripts/test-coldboot.sh <iterations>
#
# PASS per boot = /health/ready 200 AND /account login matches AND
#                 trade_allowed && trade_expert both true.
set -uo pipefail

iters="${1:-3}"
: "${MT5_LOGIN:?set MT5_LOGIN}" "${MT5_PASSWORD:?set MT5_PASSWORD}" "${MT5_SERVER:?set MT5_SERVER}"
export MT5_LOGIN MT5_PASSWORD MT5_SERVER
pass=0

for i in $(seq 1 "$iters"); do
  echo "── boot $i/$iters ──"
  docker compose down -v >/dev/null 2>&1 || true
  rm -rf ./config && mkdir -p ./config
  docker compose up -d --build >/dev/null

  ready=""
  for _ in $(seq 1 120); do            # up to 10 min (install + login)
    if curl -sf http://localhost:5001/health/ready >/dev/null 2>&1; then ready=1; break; fi
    sleep 5
  done

  acct="$(curl -s http://localhost:5001/account || true)"
  read -r login te < <(printf '%s' "$acct" | python3 -c \
'import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("login", ""), d.get("trade_allowed") and d.get("trade_expert"))
except Exception:
    print("", "")' 2>/dev/null)

  if [ "$ready" = "1" ] && [ "$login" = "$MT5_LOGIN" ] && [ "$te" = "True" ]; then
    echo "  PASS  login=$login autotrading=$te"
    pass=$((pass + 1))
  else
    echo "  FAIL  ready=${ready:-0} login=${login:-none} autotrading=${te:-none}"
    docker compose logs --tail 25 mt5 2>/dev/null || true
  fi
done

echo "RESULT: $pass/$iters passed"
docker compose down -v >/dev/null 2>&1 || true
[ "$pass" -eq "$iters" ]
