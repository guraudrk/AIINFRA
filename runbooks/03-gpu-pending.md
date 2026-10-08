# 03. GPU 부족으로 Pending

> 재현: `make chaos SCENARIO=3` / 원복: `make chaos-revert SCENARIO=3`

## 증상
GPU를 더 할당하는 변경 후 AI 서비스 응답 없음. 노드는 모두 정상.

## 영향
LLM 0개 (Recreate 전략이라 옛 Pod를 먼저 삭제)

## 확인 명령 (실제 출력 일부)
```bash
kubectl -n ai-platform get pods                      # llm-serving Pending
kubectl -n ai-platform describe pod -l app.kubernetes.io/name=llm-serving | tail -5
#   0/4 nodes are available: 1 Insufficient nvidia.com/gpu, 1 node(s) didn't match Pod's node affinity/selector,
#   2 node(s) had untolerated taint(s). preemption: 0/4 nodes are available: 4 Preemption is not helpful   <- 실제 출력
kubectl describe node ax-lab-worker2 | grep -A8 "Allocated resources"   # GPU 용량 2, 임베딩이 1 사용
```

## 원인
LLM GPU 요청 1 → 3. 클러스터 GPU 총 2개 → 배치 가능한 노드 없음

## 조치
GPU 요청 원복(1). 정말 필요하면 GPU 노드 증설 또는 MIG·time-slicing

## 재발 방지
- 배포 전 용량 확인 (Allocated resources)
- ResourceQuota로 네임스페이스 GPU 상한 관리
- --wait --rollback-on-failure
