#!/usr/bin/env python3
"""게이트웨이 부하 생성: 여러 역할로 동시에 질문을 보낸다 (모니터링·HPA·장애 시나리오용).

  DEMO_PASSWORD=... python3 scripts/load-gateway.py --concurrency 6 --rounds 1
  기본 접속: https://localhost (사내 CA: infra/tls/hanbit-root-ca.crt)
"""
import argparse
import json
import os
import ssl
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS = [
    ("maint01", "3호기 E-203 대응 방법과 최근 정비 이력 알려줘"),
    ("worker01", "3호기에 E-203 경보가 떴어요. 어떻게 해야 하나요?"),
    ("quality01", "프레스 3호기 성형 깊이 불량 원인이 뭐였어?"),
    ("admin01", "CNC 2호기 E-302 경보 대응 방법 알려줘"),
    ("maint01", "프레스 3호기 E-203 조치에 필요한 부품 재고 있어?"),
    ("worker01", "광커튼이 차단됐을 때 작업자 행동 요령 알려줘"),
]


def call(base, ctx, path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=600, context=ctx) as resp:
        return json.load(resp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://localhost")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--rounds", type=int, default=1)
    args = ap.parse_args()
    ctx = ssl.create_default_context(cafile=os.path.join(ROOT, "infra/tls/hanbit-root-ca.crt"))
    tokens = {u: call(args.base, ctx, "/api/login", {"username": u, "password": os.environ["DEMO_PASSWORD"]})["token"]
              for u in {q[0] for q in QUESTIONS}}
    results = []

    def worker(i):
        user, q = QUESTIONS[i % len(QUESTIONS)]
        start = time.perf_counter()
        try:
            r = call(args.base, ctx, "/api/chat", {"question": q}, tokens[user])
            results.append(("ok", user, time.perf_counter() - start, len(r["sources"])))
        except Exception as e:
            results.append((f"error {e}", user, time.perf_counter() - start, 0))

    for rnd in range(args.rounds):
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.concurrency)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    for status, user, sec, n in results:
        print(f"{status:6} {user:10} {sec:6.1f}s 출처 {n}개")


if __name__ == "__main__":
    main()
