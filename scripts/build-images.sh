#!/usr/bin/env bash
# 앱 이미지를 로컬에서 빌드하고 kind 노드에 직접 넣는다 (레지스트리 없이).
# 폐쇄망에서도 같은 방식: 이미지를 tar로 반입 → 노드(또는 내부 레지스트리)에 적재.
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=ax-lab
build() {
  local name=$1 dir=$2
  echo "[build] $name ($dir)"
  docker build -q -t "$name" "$dir" >/dev/null
  kind load docker-image "$name" --name "$CLUSTER" >/dev/null
  echo "[build] $name → kind 노드 적재 완료"
}

build ax/ingest:0.1.0 apps/ingest
build ax/ax-gateway:0.1.2 apps/ax-gateway
build ax/web-ui:0.1.0 apps/web-ui
