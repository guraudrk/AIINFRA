#!/usr/bin/env bash
# Prometheus에 PromQL을 던져 결과를 한 줄씩 보여 준다 (port-forward 자동).
#   ./scripts/prom-query.sh 'up{namespace="ai-platform"}'
#   ./scripts/prom-query.sh --alerts          # 발생 중(firing)·대기(pending) 알람 목록
set -euo pipefail
PORT=19090
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus "$PORT":9090 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null' EXIT
for _ in $(seq 1 20); do curl -s "localhost:$PORT/-/ready" >/dev/null 2>&1 && break; sleep 0.5; done

if [[ "${1:-}" == "--alerts" ]]; then
  curl -s "localhost:$PORT/api/v1/alerts" | python3 -c '
import sys, json
alerts = [a for a in json.load(sys.stdin)["data"]["alerts"] if a["labels"].get("severity") in ("critical", "warning")]
for a in sorted(alerts, key=lambda a: a["state"]):
    print(f"{a["state"]:8} {a["labels"]["severity"]:8} {a["labels"]["alertname"]:22} {a["annotations"].get("summary", "")}")
print(f"(총 {len(alerts)}건)")'
  exit 0
fi

curl -s "localhost:$PORT/api/v1/query" --data-urlencode "query=$1" | python3 -c '
import sys, json
for r in json.load(sys.stdin)["data"]["result"]:
    labels = ",".join(f"{k}={v}" for k, v in r["metric"].items() if k not in ("__name__", "endpoint", "instance", "container", "service", "prometheus"))
    print(f"{r["value"][1]:>12}  {labels}")'
