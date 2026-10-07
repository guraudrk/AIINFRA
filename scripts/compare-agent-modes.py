#!/usr/bin/env python3
"""에이전트 방식 비교: 현재 게이트웨이 모드(AGENT_MODE)로 질문 세트를 보내 도구 선택 정확도를 잰다.

관리자 계정(모든 도구 허용)으로 보내므로 권한 거부 없이 "모델이 무엇을 골랐는지"만 본다.
  DEMO_PASSWORD=... python3 scripts/compare-agent-modes.py
"""
import json
import os
import urllib.request

BASE = os.environ.get("BASE_URL", "http://localhost:18000")
CASES = [  # (질문, 반드시 있어야 할 도구, 있으면 안 되는 도구)
    ("3호기 E-203 대응 방법과 최근 정비 이력 알려줘", {"search_docs", "query_maintenance"}, set()),
    ("프레스 3호기 E-203 조치에 필요한 부품 재고 있어?", {"check_stock"}, {"draft_ticket"}),
    ("CNC 2호기 E-302 경보 정비 요청 접수해줘", {"draft_ticket"}, set()),
    ("광커튼이 차단됐을 때 작업자 행동 요령 알려줘", {"search_docs"}, {"query_maintenance", "check_stock"}),
]


def call(path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)


token = call("/api/login", {"username": "admin01", "password": os.environ["DEMO_PASSWORD"]})["token"]
ok = 0
print("| 질문 | 선택된 도구 | 판정 | 시간(s) |\n|---|---|---|---|")
for q, must, must_not in CASES:
    r = call("/api/chat", {"question": q}, token)
    used = set(r["tools_used"])
    passed = must <= used and not (must_not & used)
    ok += passed
    print(f"| {q} | {', '.join(r['tools_used'])} | {'✅' if passed else '❌'} | {r['elapsed_sec']} |")
print(f"\n모드 {r['mode']}: {ok}/{len(CASES)} 정확")
