#!/usr/bin/env python3
"""같은 질문을 4개 역할로 보내 응답 범위를 비교한다 (수동 확인용).

  kubectl -n ai-platform port-forward svc/ax-gateway 18000:8000 &
  DEMO_PASSWORD=... python3 scripts/ask-all-roles.py "3호기 E-203 대응 방법과 최근 정비 이력 알려줘"
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("BASE_URL", "http://localhost:18000")
PASSWORD = os.environ["DEMO_PASSWORD"]
QUESTION = sys.argv[1] if len(sys.argv) > 1 else "3호기 E-203 대응 방법과 최근 정비 이력 알려줘"


def call(path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)


for user in ["worker01", "maint01", "quality01", "admin01"]:
    token = call("/api/login", {"username": user, "password": PASSWORD})["token"]
    r = call("/api/chat", {"question": QUESTION}, token)
    parsed = {k: v for k, v in r["parsed"].items() if v}
    print(f"\n===== {user} ({r['elapsed_sec']}s) parsed={parsed}")
    print("sources:", [(s["doc_id"], s["access_level"], s["section"][:16], s["distance"]) for s in r["sources"]])
    print("tools:", r["tools_used"], "denied:", r["denied"])
    for tool, rows in r["results"].items():
        print(f"  {tool}: {str(rows)[:200]}")
    print("answer:\n" + r["answer"])
