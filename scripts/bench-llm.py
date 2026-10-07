#!/usr/bin/env python3
"""LLM 서빙 벤치마크: 동시 요청 수별 TTFT, 토큰/초, 전체 응답 시간.

OpenAI 호환 API(/v1/chat/completions, stream)를 쓰므로 Ollama와 vLLM 모두에 쓸 수 있다.
표준 라이브러리만 사용한다(설치 불필요).

사용 예:
  kubectl -n ai-platform port-forward svc/llm-serving 11434:11434 &
  python3 scripts/bench-llm.py --url http://localhost:11434 --model qwen2.5:3b --concurrency 1,4,8

측정 항목
  TTFT        요청을 보낸 뒤 첫 토큰이 도착할 때까지 시간 (사용자가 "반응이 왔다"고 느끼는 시간)
  토큰/초     첫 토큰 이후 생성 속도 = 생성 토큰 수 / (전체 시간 - TTFT)  (요청 1개 기준)
  전체 시간   요청 시작부터 마지막 토큰까지
  총 처리량   모든 요청의 생성 토큰 합 / 해당 라운드 벽시계 시간 (서버 전체 처리 능력)
"""
import argparse
import json
import statistics
import threading
import time
import urllib.request

PROMPT = (
    "한빛정밀 프레스 3호기에서 경보 코드 E-203(유압 압력 저하)이 발생했다. "
    "현장 작업자가 바로 할 수 있는 점검 순서를 5단계로 짧게 알려줘."
)


def one_request(url, model, max_tokens, results, idx):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream_options": {"include_usage": True},
    }).encode()
    req = urllib.request.Request(
        f"{url}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    ttft = None
    chunks = 0
    usage_tokens = None
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            for raw in resp:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                obj = json.loads(data)
                if obj.get("usage"):
                    usage_tokens = obj["usage"].get("completion_tokens")
                for choice in obj.get("choices", []):
                    if choice.get("delta", {}).get("content"):
                        if ttft is None:
                            ttft = time.perf_counter() - start
                        chunks += 1
        total = time.perf_counter() - start
        tokens = usage_tokens or chunks  # usage가 없으면 스트림 조각 수로 근사
        decode = max(total - (ttft or total), 1e-6)
        results[idx] = {"ttft": ttft, "total": total, "tokens": tokens, "tps": tokens / decode}
    except Exception as e:  # 실패도 결과로 남긴다
        results[idx] = {"error": str(e)}


def run_round(url, model, concurrency, max_tokens):
    results = [None] * concurrency
    threads = [threading.Thread(target=one_request, args=(url, model, max_tokens, results, i))
               for i in range(concurrency)]
    wall_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall_start
    ok = [r for r in results if r and "error" not in r]
    errors = [r["error"] for r in results if r and "error" in r]
    return ok, errors, wall


def p95(values):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--model", default="qwen2.5:3b")
    ap.add_argument("--concurrency", default="1,4,8")
    ap.add_argument("--max-tokens", type=int, default=128)
    args = ap.parse_args()

    print(f"워밍업 요청 1회 (모델 로딩 시간 제외) ... ", end="", flush=True)
    run_round(args.url, args.model, 1, 8)
    print("완료\n")

    header = "| 동시 요청 | 성공 | TTFT 평균(s) | TTFT p95(s) | 토큰/초(요청당 평균) | 전체 시간 평균(s) | 총 처리량(토큰/s) |"
    print(header)
    print("|" + "---|" * 7)
    for c in [int(x) for x in args.concurrency.split(",")]:
        ok, errors, wall = run_round(args.url, args.model, c, args.max_tokens)
        if not ok:
            print(f"| {c} | 0/{c} | - | - | - | - | - |  오류: {errors[:1]}")
            continue
        ttfts = [r["ttft"] for r in ok if r["ttft"] is not None]
        print(f"| {c} | {len(ok)}/{c} "
              f"| {statistics.mean(ttfts):.2f} | {p95(ttfts):.2f} "
              f"| {statistics.mean(r['tps'] for r in ok):.1f} "
              f"| {statistics.mean(r['total'] for r in ok):.2f} "
              f"| {sum(r['tokens'] for r in ok) / wall:.1f} |")
        if errors:
            print(f"  └ 실패 {len(errors)}건: {errors[:1]}")


if __name__ == "__main__":
    main()
