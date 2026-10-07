#!/usr/bin/env bash
# 비밀값을 무작위로 만들어 Kubernetes Secret으로 넣는다. 코드·Git에는 비밀값을 남기지 않는다.
# 이미 있는 Secret은 덮어쓰지 않는다 (DB가 옛 비밀번호로 초기화돼 있으면 접속이 끊기므로).
set -euo pipefail

NS="${NS:-ai-platform}"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

rand() { openssl rand -base64 24 | tr -d '/+=' | cut -c1-24; }

create_if_missing() {
  local name=$1; shift
  if kubectl -n "$NS" get secret "$name" >/dev/null 2>&1; then
    echo "[secrets] $name 이미 있음 → 유지"
  else
    kubectl -n "$NS" create secret generic "$name" "$@" >/dev/null
    echo "[secrets] $name 생성"
  fi
}

# PostgreSQL: 관리자(postgres) / 수집 파이프라인(ax_ingest) / 앱(ax_app, M4 RLS 대상)
create_if_missing postgres-credentials \
  --from-literal=postgres-password="$(rand)" \
  --from-literal=ingest-password="$(rand)" \
  --from-literal=app-password="$(rand)"

# MinIO 루트 계정
create_if_missing minio-credentials \
  --from-literal=root-user="hanbit-admin" \
  --from-literal=root-password="$(rand)"
