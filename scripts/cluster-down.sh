#!/usr/bin/env bash
# kind 클러스터 삭제. 클러스터 안의 데이터(PVC 포함)가 모두 사라지므로 확인을 받는다.
set -euo pipefail

CLUSTER=ax-lab
if [[ "${FORCE:-}" != "yes" ]]; then
  read -r -p "'$CLUSTER' 클러스터와 안의 데이터를 모두 삭제합니다. 계속할까요? (yes/no) " answer
  [[ "$answer" == "yes" ]] || { echo "취소했습니다."; exit 1; }
fi
kind delete cluster --name "$CLUSTER"
