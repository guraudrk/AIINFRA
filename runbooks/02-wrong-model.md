# 02. 존재하지 않는 모델 이름 (READY 0/1)

> 재현: `make chaos SCENARIO=2` / 원복: `make chaos-revert SCENARIO=2`

## 증상
모델 업그레이드 후 AI가 답을 못 함. 배포 도구는 "성공(deployed)".

## 영향
LLM 답변 기능 전체 중단

## 확인 명령 (실제 출력 일부)
```bash
kubectl -n ai-platform get pods                      # llm-serving Running 이지만 READY 0/1
kubectl -n ai-platform describe pod -l app.kubernetes.io/name=llm-serving | tail -8
#   Readiness probe failed: Error: model 'qwen2.5:3b-instruct-q8' not found   <- 실제 출력
kubectl -n ai-platform exec deploy/llm-serving -- ollama list   # PVC에 있는 모델
```

## 원인
PVC에 없는 모델 이름으로 변경. 폐쇄망 정책(egress 차단)이라 다운로드도 불가 → readiness 실패 → Service 엔드포인트에서 제외

## 조치
모델 이름 원복. 새 모델이 필요하면 반입 → PVC 적재 → 이름 변경 순서 (docs/airgap-install.md)

## 재발 방지
- `helm upgrade --wait --rollback-on-failure`: 준비 실패 시 자동 롤백 (배포 성공 ≠ 서비스 정상)
- 모델 변경 체크리스트에 PVC 존재 확인
- 스테이징 선검증
