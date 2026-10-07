#!/usr/bin/env bash
# 1) 로컬 data/ 를 ConfigMap으로 클러스터에 넣고, upload Job이 MinIO raw-docs 버킷에 올린다
# 2) CronJob 템플릿으로 수집 Job을 즉시 1회 실행한다 (정형 CSV + 문서 청크·임베딩)
set -euo pipefail
cd "$(dirname "$0")/.."
NS="${NS:-ai-platform}"

# kubectl wait --for=condition=complete 는 Job이 실패해도 시간 초과까지 기다린다 → 성공/실패를 둘 다 감시
wait_job() {
  local job=$1 timeout=$2 waited=0
  while (( waited < timeout )); do
    if [[ "$(kubectl -n "$NS" get job "$job" -o jsonpath='{.status.succeeded}')" == "1" ]]; then return 0; fi
    if kubectl -n "$NS" get job "$job" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' | grep -q True; then
      echo "[ingest] $job 실패 — 로그:"; kubectl -n "$NS" logs "job/$job" --tail=30; return 1
    fi
    sleep 3; waited=$((waited + 3))
  done
  echo "[ingest] $job 시간 초과(${timeout}s)"; return 1
}

echo "[ingest] data/ → ConfigMap (원본 문서 $(ls data/docs | wc -l)개, CSV $(ls data/csv | wc -l)개)"
kubectl -n "$NS" create configmap raw-docs --from-file=data/docs --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n "$NS" create configmap raw-csv  --from-file=data/csv  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# upload Job: CronJob과 같은 이미지·환경변수를 쓰되 모드만 upload, 원본 ConfigMap을 /src에 마운트
JOB="upload-$(date +%s)"
kubectl -n "$NS" create job "$JOB" --from=cronjob/ingest --dry-run=client -o json | python3 -c '
import sys, json
job = json.load(sys.stdin)
pod = job["spec"]["template"]["spec"]
c = pod["containers"][0]
c["args"] = ["upload"]
c["volumeMounts"] = [{"name": "docs", "mountPath": "/src/docs"}, {"name": "csv", "mountPath": "/src/csv"}]
pod["volumes"] = [{"name": "docs", "configMap": {"name": "raw-docs"}}, {"name": "csv", "configMap": {"name": "raw-csv"}}]
json.dump(job, sys.stdout)' | kubectl apply -f - >/dev/null
wait_job "$JOB" 180
kubectl -n "$NS" logs "job/$JOB"

JOB="ingest-$(date +%s)"
echo "[ingest] 수집 Job 실행: $JOB"
kubectl -n "$NS" create job "$JOB" --from=cronjob/ingest >/dev/null
wait_job "$JOB" 900
kubectl -n "$NS" logs "job/$JOB" | grep -E '"event": "(table_loaded|docs_done)"'
