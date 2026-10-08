# 08. 문서·청크 테이블 유실 → 백업 복구

> 재현: `make chaos SCENARIO=8` / 원복: `make chaos-revert SCENARIO=8`

## 증상
AI 검색 전체 불가(503).

## 영향
문서 검색·답변 중단

## 확인 명령 (실제 출력 일부)
```bash
SELECT count(*) FROM documents;   -- ERROR: relation does not exist
kubectl -n ai-platform get cronjob pg-backup   # 마지막 성공 시각
./scripts/prom-query.sh 'time() - kube_cronjob_status_last_successful_time{cronjob="pg-backup"}'
```

## 원인
운영자 실수로 DROP TABLE

## 조치
`make restore` (최신 백업 pg_restore --clean --single-transaction) → 행 수·RLS 정책·질문 확인. 실측 RTO 48초 / RPO 36초 (docs/restore-drill-report.md)

## 재발 방지
- 운영 DB 직접 접근 권한 최소화·이중 확인
- PITR(WAL 아카이빙)로 RPO 단축
- 정기 복구 훈련
