#!/usr/bin/env bash
# 권한 테스트 실행: 게이트웨이 port-forward + 데모 비밀번호를 Secret에서 읽어 환경변수로 전달
set -euo pipefail
cd "$(dirname "$0")/.."
NS="${NS:-ai-platform}"
PORT=18000

export DEMO_PASSWORD
DEMO_PASSWORD=$(kubectl -n "$NS" get secret gateway-secrets -o jsonpath='{.data.demo-password}' | base64 -d)
kubectl -n "$NS" port-forward svc/ax-gateway "$PORT":8000 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null' EXIT
sleep 3

# 결과를 항상 파일로도 남긴다 (간헐적 실패의 원인을 나중에 볼 수 있도록)
LOG="/tmp/ax-test-$(date +%Y%m%d-%H%M%S).log"
BASE_URL="http://localhost:$PORT" python3 -m unittest -v tests/test_permissions.py 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
echo "테스트 로그: $LOG"
exit "$status"
