#!/usr/bin/env bash
# 폐쇄망 설치 후 인수 검증: 외부 차단 유지 · HTTPS 입구 · 네트워크 정책 · 권한 RAG
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
check() { if eval "$2"; then echo "✅ $1"; else echo "❌ $1"; fail=1; fi; }

check "노드에서 외부 인터넷 차단 유지" "! docker exec ax-lab-worker2 curl -s -m 5 -o /dev/null https://registry.ollama.ai"
check "Pod에서 외부 인터넷 차단" "! kubectl -n ai-platform exec deploy/ax-gateway -- python -c \"import socket; socket.create_connection(('1.1.1.1',443),timeout=3)\" 2>/dev/null"
check "모든 ai-platform Pod 정상" "! kubectl -n ai-platform get pods --no-headers | grep -vE 'Running|Completed' | grep -q ."
check "HTTPS 입구(사내 CA 검증)" "curl -sf -o /dev/null --cacert infra/tls/hanbit-root-ca.crt https://localhost/"
echo; echo "── NetworkPolicy"; ./scripts/netpol-test.sh | tail -1 || fail=1
echo; echo "── 권한 기반 RAG 테스트"; ./scripts/run-tests.sh 2>&1 | grep -E "^Ran |^OK|^FAILED" || fail=1
echo; [[ $fail -eq 0 ]] && echo "인수 검증 통과" || echo "인수 검증 실패 항목 있음"
exit $fail
