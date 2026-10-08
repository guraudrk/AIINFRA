# 06. 요청 폭주 → 대기열 → TTFT 악화

> 재현: `make chaos SCENARIO=6` / 원복: `make chaos-revert SCENARIO=6`

## 증상
교대 직후 답변이 1~2분 걸림.

## 영향
응답 지연 (오류는 아님)

## 확인 명령 (실제 출력 일부)
```bash
./scripts/prom-query.sh "sum(ax_llm_inflight)"       # 5 > 슬롯 4 (M6 실측)
./scripts/prom-query.sh --alerts                     # LLMQueueBacklog firing, LLMTTFTHigh pending
# Grafana AX · AI 플랫폼: 대기열·TTFT p95(약 1분) 패널 (docs/images/m6-grafana-ai-platform.png)
```

## 원인
동시 요청 수가 LLM 동시 슬롯(num_parallel=4)과 CPU 처리 능력을 초과

## 조치
단기: 동시성 제한(초과 요청은 빠른 안내 응답), 프롬프트 축소(TOP_K) / 중기: llm-serving 레플리카·GPU 증설

## 재발 방지
- 게이트웨이 HPA는 CPU 기준이라 LLM 병목에는 효과가 없다 → LLM 쪽 용량이 핵심
- 대기열 알람을 TTFT 알람의 앞단 신호로 운영
- 사이징 시 동시 사용자 기준 슬롯 수 산정 (M9)
