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

# 게이트웨이: JWT 서명 키, 데모 사용자 공용 비밀번호
create_if_missing gateway-secrets \
  --from-literal=jwt-secret="$(openssl rand -hex 32)" \
  --from-literal=demo-password="$(rand | cut -c1-12)"

# 이미 있는 Secret에 키만 추가 (기존 키는 건드리지 않음)
add_key_if_missing() {
  local ns=$1 name=$2 key=$3
  if [[ -z "$(kubectl -n "$ns" get secret "$name" -o jsonpath="{.data.$key}" 2>/dev/null)" ]]; then
    kubectl -n "$ns" patch secret "$name" --type=merge -p "{\"stringData\":{\"$key\":\"$(rand)\"}}" >/dev/null
    echo "[secrets] $name/$key 추가"
  fi
}
# M6: PostgreSQL 모니터링 전용 계정(ax_monitor, pg_monitor 권한만) 비밀번호
add_key_if_missing "$NS" postgres-credentials monitor-password

# M6: Grafana 관리자 (monitoring 네임스페이스)
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - >/dev/null
NS=monitoring create_if_missing grafana-admin \
  --from-literal=admin-user="admin" \
  --from-literal=admin-password="$(rand)"
