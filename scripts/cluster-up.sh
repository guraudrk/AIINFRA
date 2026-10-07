#!/usr/bin/env bash
# kind 클러스터 생성 → Calico 설치 → (SIMULATED면) 가짜 GPU 등록
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=ax-lab
CALICO_VERSION="${CALICO_VERSION:-v3.33.0}"
GPU_MODE="${GPU_MODE:-SIMULATED}"   # docs/00-environment.md 참고

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  echo "[cluster-up] '$CLUSTER' 클러스터가 이미 있습니다. 건너뜀."
else
  echo "[cluster-up] kind 클러스터 생성 (4노드)"
  kind create cluster --config infra/kind-config.yaml
fi

echo "[cluster-up] Calico $CALICO_VERSION 설치"
kubectl apply -f "https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/calico.yaml" >/dev/null

echo "[cluster-up] CNI가 올라와 모든 노드가 Ready 될 때까지 대기"
kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
kubectl wait --for=condition=Ready nodes --all --timeout=300s

if [[ "$GPU_MODE" == "SIMULATED" ]]; then
  ./scripts/fake-gpu.sh 2
fi

kubectl get nodes -L node-role
