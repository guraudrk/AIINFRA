#!/usr/bin/env bash
# 폐쇄망 설치 리허설: 반입 번들(airgap/)만으로 클러스터를 처음부터 구성한다.
# 클러스터 생성 직후 노드의 외부 인터넷을 차단하므로, 번들에 없는 것이 하나라도 있으면 실패한다.
#   FORCE=yes ./scripts/airgap-install.sh     (기존 ax-lab 클러스터를 삭제하고 진행)
set -euo pipefail
cd "$(dirname "$0")/.."
B=airgap
NS=ai-platform
CLUSTER=ax-lab
START=$(date +%s)
step() { printf "\n[%4ss] ▶ %s\n" "$(( $(date +%s) - START ))" "$*"; }

step "0. 번들 무결성 검증 (SHA256)"
(cd "$B" && sha256sum -c SHA256SUMS --quiet) && echo "    체크섬 일치"

step "1. 기존 클러스터 삭제 → kind 클러스터 생성 (노드 이미지는 번들에서)"
docker image inspect "$(cat $B/node-image.txt)" >/dev/null 2>&1 || docker load -q -i "$B/images/kind-node.tar"
if kind get clusters | grep -qx "$CLUSTER"; then FORCE="${FORCE:-}" ./scripts/cluster-down.sh; fi
kind create cluster --config infra/kind-config.yaml --image "$(cat $B/node-image.txt)"

step "2. 노드 외부 인터넷 차단 + 확인"
./scripts/block-egress.sh
if docker exec "$CLUSTER-control-plane" curl -s -m 5 -o /dev/null https://registry-1.docker.io; then
  echo "    ❌ 외부 접속이 아직 가능합니다"; exit 1
else
  echo "    ✅ 외부 레지스트리 접속 불가 (폐쇄망 상태)"
fi

step "3. 컨테이너 이미지 적재 (Ollama는 GPU 노드에만)"
for tar in "$B"/images/*.tar; do
  [[ "$tar" == *kind-node.tar ]] && continue
  if [[ "$tar" == *ollama* ]]; then
    kind load image-archive "$tar" --name "$CLUSTER" --nodes "$CLUSTER-worker2" >/dev/null
  else
    kind load image-archive "$tar" --name "$CLUSTER" >/dev/null
  fi
  echo "    적재 $(basename "$tar")"
done

step "4. CNI(Calico) · metrics-server"
kubectl apply -f infra/vendor/calico-v3.33.0.yaml >/dev/null
kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s >/dev/null
kubectl wait --for=condition=Ready nodes --all --timeout=300s >/dev/null
kubectl apply -f infra/vendor/metrics-server-v0.9.0.yaml >/dev/null
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' >/dev/null
./scripts/fake-gpu.sh 2

step "5. cert-manager · 사내 CA · Traefik"
kubectl apply -f infra/vendor/cert-manager-v1.21.2.yaml >/dev/null
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=300s >/dev/null
until kubectl apply -f infra/tls/issuers.yaml >/dev/null 2>&1; do sleep 3; done   # webhook이 요청을 받을 때까지
kubectl -n cert-manager wait --for=condition=Ready certificate/hanbit-root-ca --timeout=120s >/dev/null
helm upgrade --install traefik infra/vendor/traefik-41.6.1.tgz -n traefik --create-namespace -f infra/traefik-values.yaml >/dev/null
kubectl -n traefik rollout status deploy/traefik --timeout=300s >/dev/null
kubectl -n cert-manager get secret hanbit-root-ca -o jsonpath='{.data.ca\.crt}' | base64 -d > infra/tls/hanbit-root-ca.crt

step "6. 비밀값 생성 · 플랫폼 차트 설치"
./scripts/create-secrets.sh
helm upgrade --install ai-platform charts/ai-platform -n "$NS" --create-namespace --wait=false >/dev/null

step "7. 모델 복원 (인터넷 다운로드 대신 반입 파일을 PVC에 풀기)"
for svc in llm-serving embedding-serving; do
  kubectl -n "$NS" wait --for=condition=PodReadyToStartContainers pod -l app.kubernetes.io/name=$svc --timeout=600s >/dev/null
  until kubectl -n "$NS" exec deploy/$svc -- true 2>/dev/null; do sleep 3; done
  kubectl -n "$NS" exec -i deploy/$svc -- tar -C /root/.ollama -xf - < "$B/models/$svc.tar"
  echo "    복원 $svc"
done
kubectl -n "$NS" rollout status deploy/llm-serving --timeout=600s >/dev/null
kubectl -n "$NS" rollout status deploy/embedding-serving --timeout=600s >/dev/null

step "8. 데이터 수집 (가상 데이터 → MinIO → pgvector)"
kubectl -n "$NS" rollout status statefulset/postgres --timeout=300s >/dev/null
kubectl -n "$NS" rollout status statefulset/minio --timeout=300s >/dev/null
kubectl -n "$NS" rollout status deploy/ax-gateway --timeout=300s >/dev/null
./scripts/ingest.sh

step "9. 설치 완료 — 소요 $(( $(date +%s) - START ))초. 검증은 scripts/airgap-verify.sh"
