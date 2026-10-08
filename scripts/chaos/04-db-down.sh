#!/usr/bin/env bash
# 시나리오 4: PostgreSQL Pod 강제 삭제 → 일시적 연결 실패 → StatefulSet 재생성 후 앱이 스스로 재연결하는지
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    echo "[$(date +%T)] postgres-0 강제 삭제"
    kubectl -n "$NS" delete pod postgres-0 --grace-period=0 --force >/dev/null 2>&1
    for i in 1 2 3 4 5 6 7 8; do
      printf "[%s] gateway readyz=%s  " "$(date +%T)" \
        "$(kubectl -n "$NS" exec deploy/ax-gateway -- python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/readyz', timeout=5).status)" 2>/dev/null || echo 503)"
      kubectl -n "$NS" get pod postgres-0 --no-headers 2>/dev/null | awk '{print "postgres-0", $2, $3}' || echo "postgres-0 없음"
      sleep 5
    done ;;
  revert) kubectl -n "$NS" rollout status statefulset/postgres --timeout=300s >/dev/null; echo "원복 완료(StatefulSet이 자동 재생성)" ;;
  *) usage ;;
esac
