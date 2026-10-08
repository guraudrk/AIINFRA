# 04. PostgreSQL Pod 중단과 자동 복구

> 재현: `make chaos SCENARIO=4` / 원복: `make chaos-revert SCENARIO=4`

## 증상
수 초간 질문 오류 후 자동 회복.

## 영향
DB 재기동 약 9초 동안 게이트웨이 readyz 503 (트래픽에서 제외)

## 확인 명령 (실제 출력 일부)
```bash
kubectl -n ai-platform get pod postgres-0 -w
./scripts/chaos/04-db-down.sh inject     # 5초 간격으로 readyz와 Pod 상태 추적
#   17:35:27 readyz=503 postgres-0 ContainerCreating → 17:35:36 readyz=200 Running   <- 실제 출력
```

## 원인
Pod 강제 삭제 (노드 장애·축출 상황 재현)

## 조치
StatefulSet이 같은 이름·같은 PVC로 자동 재생성. 게이트웨이 연결 풀이 끊긴 연결을 검사 후 교체해서 앱 재시작 불필요

## 재발 방지
- readiness는 DB 연결, liveness는 프로세스만 검사 (DB 장애로 앱을 재시작하지 않음)
- 운영은 DB HA(Patroni, CloudNativePG, EDB)로 장애 전환
