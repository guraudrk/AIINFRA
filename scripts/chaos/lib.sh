#!/usr/bin/env bash
# 장애 시나리오 공통 함수. 장애는 Helm 값으로만 주입하고(kubectl 직접 수정 금지 — M4 교훈),
# 원복은 "차트 기본값으로 다시 배포"한다.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
NS=ai-platform

helm_set() {   # helm_set --set a=b ...   (장애 주입)
  helm upgrade ai-platform charts/ai-platform -n "$NS" "$@" >/dev/null
}
helm_reset() { # 기본값으로 원복
  # --reset-values 를 명시해야 한다. 없으면 직전 릴리스에서 --set 으로 덮어쓴 값이 다시 적용되어
  # "원복 배포는 성공했는데 장애 설정은 그대로"가 된다 (M8에서 실제로 겪음)
  helm upgrade ai-platform charts/ai-platform -n "$NS" --reset-values >/dev/null
  local left; left=$(helm get values ai-platform -n "$NS" -o json)
  [[ "$left" == "null" || "$left" == "{}" ]] || { echo "⚠️ 원복 후에도 덮어쓴 값이 남아 있음: $left"; return 1; }
}

# 사용자 입장에서 질문 한 번 (HTTPS 입구 경유). 결과만 한 줄로.
ask() {  # ask <user> <question>
  local pw; pw=$(kubectl -n "$NS" get secret gateway-secrets -o jsonpath='{.data.demo-password}' | base64 -d)
  python3 - "$1" "$pw" "$2" <<'EOF'
import json, ssl, sys, urllib.request, urllib.error
user, pw, q = sys.argv[1:4]
ctx = ssl.create_default_context(cafile="infra/tls/hanbit-root-ca.crt")
def call(path, body, tok=None):
    h = {"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})}
    return json.load(urllib.request.urlopen(urllib.request.Request("https://localhost" + path, json.dumps(body).encode(), h), timeout=300, context=ctx))
try:
    tok = call("/api/login", {"username": user, "password": pw})["token"]
    r = call("/api/chat", {"question": q}, tok)
    print(f"응답 OK ({r['elapsed_sec']}s) 출처={[s['doc_id'] for s in r['sources']]} 거부={r['denied']}")
    print("답변:", r["answer"][:300].replace("\n", " "))
except urllib.error.HTTPError as e:
    print(f"오류 HTTP {e.code}: {e.read().decode()[:200]}")
except Exception as e:
    print(f"오류 {type(e).__name__}: {e}")
EOF
}

ticket() {  # 고객 문의 형태로 증상만 출력
  echo
  echo "┌─ 📞 고객 문의 ───────────────────────────────────────────"
  printf "│ %s\n" "$@"
  echo "└──────────────────────────────────────────────────────────"
  echo "→ 원인을 직접 찾아 보세요. 막히면 \"힌트\"라고 말해 주세요."
}

usage() { echo "사용법: $0 inject | revert"; exit 1; }
