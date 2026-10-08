#!/usr/bin/env bash
# GPU 시뮬레이터 장애 주입: overheat | xid79 | clear
#   ./scripts/gpu-fault.sh overheat
set -euo pipefail
TYPE="${1:?overheat | xid79 | clear}"
PORT=19400
kubectl -n ai-platform port-forward ds/gpu-sim-exporter "$PORT":9400 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null' EXIT
for _ in $(seq 1 20); do curl -s "localhost:$PORT/" >/dev/null 2>&1 && break; sleep 0.5; done
curl -s -X POST "localhost:$PORT/fault" -d "{\"type\":\"$TYPE\"}"
