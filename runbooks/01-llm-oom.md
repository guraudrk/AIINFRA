# 01. LLM 서빙 메모리 부족 (OOMKilled)

> 재현: `make chaos SCENARIO=1` / 원복: `make chaos-revert SCENARIO=1`

## 증상
질문하면 한참 기다리다 오류(503). 로그인·화면은 정상.

## 영향
LLM 답변 기능 전체 중단

## 확인 명령 (실제 출력 일부)
```bash
kubectl -n ai-platform get pods                      # llm-serving RESTARTS 증가
kubectl -n ai-platform describe pod -l app.kubernetes.io/name=llm-serving | grep -A6 "Last State"
#   Reason: OOMKilled / Exit Code: 137   <- 실제 출력 (137 = 128 + 9, SIGKILL)
kubectl -n ai-platform get deploy llm-serving -o jsonpath='{..resources.limits.memory}'   # 512Mi
helm history ai-platform -n ai-platform               # 17:07 리비전에서 limit 변경
```

## 원인
메모리 limit(512Mi)이 모델(1.9GB) + KV 캐시(0.6GB)보다 작게 배포됨 → 모델 로딩 순간 커널 OOM Killer가 강제 종료

## 조치
limit 원복(4Gi, values.yaml에 계산 근거 있음): `make chaos-revert SCENARIO=1` (helm --reset-values)

## 재발 방지
- 모델 크기 기반 메모리 하한을 values 주석으로 유지 (가중치 + KV 캐시 + 여유)
- 리소스 변경은 배포 리뷰 필수 항목
- PodRestarting 알람(M6)으로 조기 감지
