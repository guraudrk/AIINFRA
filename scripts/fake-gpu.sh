#!/usr/bin/env bash
# SIMULATED 모드: GPU 노드에 확장 리소스 nvidia.com/gpu 를 직접 등록한다.
#
# 실제 환경에서는 NVIDIA device plugin(DaemonSet)이 GPU를 찾아 kubelet에 등록하고,
# kubelet이 노드 status.capacity 에 nvidia.com/gpu: N 을 올린다.
# 여기서는 그 마지막 결과(노드 status)만 API로 직접 PATCH 한다.
# → 스케줄러 입장에서는 진짜 GPU 노드와 똑같이 보이지만, Pod 안에 GPU 장치가 들어가지는 않는다.
set -euo pipefail

COUNT="${1:-2}"
NODE=$(kubectl get nodes -l node-role=gpu -o jsonpath='{.items[0].metadata.name}')
PORT=8001

# 노드 status는 하위 리소스라 일반 kubectl patch로는 안 바뀐다 → kubectl proxy로 REST API 직접 호출
kubectl proxy --port="$PORT" >/dev/null 2>&1 &
PROXY_PID=$!
trap 'kill $PROXY_PID 2>/dev/null' EXIT
sleep 1

# JSON Patch에서 키 안의 '/'는 '~1'로 이스케이프한다 (nvidia.com/gpu → nvidia.com~1gpu)
curl -sf -X PATCH \
  -H "Content-Type: application/json-patch+json" \
  --data "[{\"op\":\"add\",\"path\":\"/status/capacity/nvidia.com~1gpu\",\"value\":\"${COUNT}\"}]" \
  "http://127.0.0.1:${PORT}/api/v1/nodes/${NODE}/status" >/dev/null

# capacity(총량)는 바로 바뀌지만 allocatable(Pod에 줄 수 있는 양)은 kubelet이 다음 상태 보고 때 계산한다
for _ in $(seq 1 30); do
  ALLOC=$(kubectl get node "$NODE" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}')
  [[ -n "$ALLOC" ]] && break
  sleep 2
done
echo "[fake-gpu] $NODE: nvidia.com/gpu capacity/allocatable = ${COUNT}/${ALLOC:-반영 안 됨}"
