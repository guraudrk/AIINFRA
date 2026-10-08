# AX Platform Lab

가상 제조사 **한빛정밀**의 권한 기반 사내 AI 플랫폼(sLLM + RAG + AI 에이전트)을
쿠버네티스 GPU 인프라에 구축하고 운영(모니터링·백업·장애 대응)·사이징까지 재현하는 개인 프로젝트입니다.

> 진행 중입니다. 아래 표는 **동작을 확인한 모듈만** 완료로 표시합니다.

## 모듈 진행 상황
| 모듈 | 내용 | 상태 |
|---|---|---|
| M0 | 환경 점검 (WSL2·Docker·GPU) | ✅ 완료 — [docs/00-environment.md](docs/00-environment.md) |
| M1 | kind 4노드 클러스터·GPU 노드 | ✅ 완료 — Calico, GPU SIMULATED(`nvidia.com/gpu: 2`), 배치 검증 |
| M2 | sLLM·임베딩 서빙 | ✅ 완료 — Ollama qwen2.5:3b + bge-m3(1024차원), CPU 벤치 동시 4개 처리량 34.8 토큰/s (vLLM 옵션은 미검증) |
| M3 | 데이터 계층 (pgvector·MinIO·수집) | ✅ 완료 — 가상 문서 18개 → 청크 138개(1024차원), 정형 7개 테이블, 변경분 수집 CronJob |
| M4 | 권한 기반 RAG + 에이전트 | ✅ 완료 — 역할 4개 × 도구 4개, 앱 필터 + PostgreSQL RLS 2중 통제, 감사 로그, 자동 테스트 14/14 통과 |
| M5 | 네트워크·보안·폐쇄망 | ✅ 완료 — Traefik+TLS(사내 CA), NetworkPolicy 14/14, 폐쇄망 재구축 15분 21초 ([절차서](docs/airgap-install.md)) |
| M6 | 모니터링·알람 | ✅ 완료 — Prometheus·Grafana(/grafana), DCGM 호환 GPU 지표, TTFT·대기열, 대시보드 2개, 알람 11종(실발생 확인) |
| M7 | 백업·복구 훈련 | ✅ 완료 — pg_dump → MinIO 일 1회(7개 보관, 실패 알람), 복구 훈련 **RTO 48초 / RPO 36초** ([보고서](docs/restore-drill-report.md)) |
| M8 | 장애 대응 런북 | ⬜ |
| M9 | 사이징·기술 제안 | ⬜ |
| M10 | 마무리 | ⬜ |

## 저장소 구조
```
infra/          kind 설정 등 클러스터 인프라
apps/           ax-gateway, web-ui, ingest, sizing, gpu-sim-exporter
charts/         Helm 차트 (ai-platform)
data/           가상 데이터 (한빛정밀)
observability/  대시보드·알람 규칙
backup/         백업 CronJob
runbooks/       장애 대응 런북
scripts/        운영 스크립트, scripts/chaos/ 장애 주입
docs/           문서, docs/study/ 면접 노트, docs/images/ 캡처
```

## 빠른 시작
사전 준비: WSL2(Ubuntu) + Docker Desktop(WSL Integration ON), kubectl·kind·helm ([docs/00-environment.md](docs/00-environment.md))
```bash
make up       # kind 4노드 + Calico + (SIMULATED) GPU 2개 등록
make images   # 앱 이미지 빌드 + kind 노드 적재
make deploy   # Secret 생성 + ai-platform 차트 설치 + 모델 사전 적재 (첫 실행 시 이미지·모델 약 7GB 다운로드)
make ingest   # 가상 데이터 → MinIO → 청크·임베딩 → pgvector
make test     # 같은 질문을 4개 역할로 보내 권한 범위·RLS·감사 로그 자동 검증
./scripts/netpol-test.sh   # NetworkPolicy 허용·차단 표
# 채팅 화면: https://localhost/  (사내 CA: infra/tls/hanbit-root-ca.crt)

# 백업·복구
make backup                                # DB 덤프 → MinIO, k8s 설정 내보내기
CONFIRM=yes ./scripts/restore-drill.sh     # 복구 훈련 (테이블 삭제 → 복구 → RTO/RPO 보고서)

# 폐쇄망 리허설
./scripts/airgap-bundle.sh                 # 반입 번들 생성 (인터넷 되는 쪽)
FORCE=yes ./scripts/airgap-install.sh      # 클러스터 삭제 → 인터넷 차단 → 번들만으로 재구축
./scripts/airgap-verify.sh                 # 인수 검증
make status   # 노드·Pod 상태
make down     # 클러스터 삭제 (확인 질문 있음)
```
