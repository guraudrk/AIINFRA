#!/usr/bin/env bash
# 시나리오 6: 동시 요청 폭주 (교대 시간 직후 질문 몰림) → 대기열 → TTFT 알람
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    export DEMO_PASSWORD; DEMO_PASSWORD=$(kubectl -n "$NS" get secret gateway-secrets -o jsonpath='{.data.demo-password}' | base64 -d)
    nohup python3 scripts/load-gateway.py --concurrency 10 > /tmp/chaos06.log 2>&1 &
    echo "동시 질문 10개 발송 (백그라운드, 결과: /tmp/chaos06.log)"
    ticket "생산팀: 교대 직후에 다들 질문하면 답이 1~2분씩 걸려요." ;;
  revert) pkill -f load-gateway.py || true; echo "부하 중지" ;;
  *) usage ;;
esac
