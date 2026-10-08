#!/usr/bin/env bash
# 플랫폼 부가 구성요소 설치 (모두 infra/vendor 고정 파일 사용, 여러 번 실행해도 안전)
#   cert-manager → 사내 CA → Traefik(입구) → kube-prometheus-stack(모니터링)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[addons] cert-manager"
kubectl apply -f infra/vendor/cert-manager-v1.21.2.yaml >/dev/null
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=300s >/dev/null
until kubectl apply -f infra/tls/issuers.yaml >/dev/null 2>&1; do sleep 3; done   # webhook 준비 대기
kubectl -n cert-manager wait --for=condition=Ready certificate/hanbit-root-ca --timeout=120s >/dev/null
kubectl -n cert-manager get secret hanbit-root-ca -o jsonpath='{.data.ca\.crt}' | base64 -d > infra/tls/hanbit-root-ca.crt

echo "[addons] Traefik (입구, HTTPS)"
helm upgrade --install traefik infra/vendor/traefik-41.6.1.tgz -n traefik --create-namespace \
  -f infra/traefik-values.yaml >/dev/null
kubectl -n traefik rollout status deploy/traefik --timeout=300s >/dev/null

echo "[addons] 모니터링 (kube-prometheus-stack)"
NS=monitoring ./scripts/create-secrets.sh >/dev/null       # grafana-admin 포함
kubectl apply -f infra/tls/grafana-cert.yaml >/dev/null
helm upgrade --install kps infra/vendor/kube-prometheus-stack-92.1.0.tgz -n monitoring \
  -f infra/monitoring-values.yaml --wait --timeout 10m >/dev/null
echo "[addons] 완료: https://localhost/ , https://localhost/grafana"
