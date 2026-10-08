#!/usr/bin/env bash
# 즉시 DB 백업: CronJob 템플릿으로 Job을 만들어 실행하고 결과(MinIO 키)를 보여 준다
set -euo pipefail
NS="${NS:-ai-platform}"
JOB="pg-backup-now-$(date +%s)"
kubectl -n "$NS" create job "$JOB" --from=cronjob/pg-backup >/dev/null
for _ in $(seq 1 100); do
  [[ "$(kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.succeeded}')" == "1" ]] && break
  if kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' | grep -q True; then
    echo "[backup] 실패"; kubectl -n "$NS" logs "job/$JOB" --all-containers --tail=20; exit 1
  fi
  sleep 3
done
kubectl -n "$NS" logs "job/$JOB" -c upload
