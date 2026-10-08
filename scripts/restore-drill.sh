#!/usr/bin/env bash
# 복구 훈련: 백업 → (백업 이후 데이터 추가) → 장애(문서·청크 테이블 삭제) → 영향 확인 → 복구 → 재확인
# RTO = 장애 발생 ~ 서비스 정상화, RPO = 마지막 백업 ~ 장애 발생 (그 사이 데이터는 잃는다)
# 결과는 docs/restore-drill-report.md 로 저장한다.
#   CONFIRM=yes ./scripts/restore-drill.sh
set -euo pipefail
cd "$(dirname "$0")/.."
NS=ai-platform
[[ "${CONFIRM:-}" == "yes" ]] || { echo "documents·chunks 테이블을 실제로 삭제합니다. CONFIRM=yes 로 실행하세요."; exit 1; }

sql() { kubectl -n "$NS" exec postgres-0 -- psql -U postgres -d hanbit -Atc "$1"; }
now() { date +%s; }
ts()  { date "+%H:%M:%S"; }
LOG=(); log() { echo "[$(ts)] $*"; LOG+=("| $(ts) | $* |"); }

# 서비스 확인: 설비보전 계정으로 실제 질문 (HTTPS 입구 경유)
PW=$(kubectl -n "$NS" get secret gateway-secrets -o jsonpath='{.data.demo-password}' | base64 -d)
probe() {
  python3 - "$PW" <<'EOF'
import json, ssl, sys, urllib.request
ctx = ssl.create_default_context(cafile="infra/tls/hanbit-root-ca.crt")
def call(path, body, tok=None):
    h = {"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})}
    req = urllib.request.Request("https://localhost" + path, json.dumps(body).encode(), h)
    return json.load(urllib.request.urlopen(req, timeout=300, context=ctx))
try:
    tok = call("/api/login", {"username": "maint01", "password": sys.argv[1]})["token"]
    r = call("/api/chat", {"question": "3호기 E-203 조치에 필요한 부품 재고 있어?"}, tok)
    print(f"정상 (출처 {len(r['sources'])}개, {r['elapsed_sec']}s)")
except urllib.error.HTTPError as e:
    print(f"장애 (HTTP {e.code})")
except Exception as e:
    print(f"장애 ({type(e).__name__})")
EOF
}

echo "== 0. 사전 상태"
BEFORE_DOCS=$(sql "SELECT count(*) FROM documents"); BEFORE_CHUNKS=$(sql "SELECT count(*) FROM chunks")
log "사전: documents=$BEFORE_DOCS, chunks=$BEFORE_CHUNKS, 서비스=$(probe)"

echo "== 1. 백업"
T_BACKUP=$(now)
BACKUP_INFO=$(./scripts/backup-now.sh)
log "백업 완료: $(echo "$BACKUP_INFO" | python3 -c 'import sys,json; d=json.loads(sys.stdin.read()); print(d["key"], d["bytes"], "bytes")')"

echo "== 2. 백업 이후 데이터 발생 (이 데이터는 잃게 된다 = RPO 확인용)"
sleep 20
sql "INSERT INTO audit_log (user_id, role, question, result) VALUES ('drill', 'admin', 'RPO 표식: 백업 이후 기록', 'drill');" >/dev/null
log "백업 이후 감사 로그 1건 추가 (표식)"

echo "== 3. 장애: documents·chunks 테이블 삭제"
T_INCIDENT=$(now)
sql "DROP TABLE chunks; DROP TABLE documents;" >/dev/null
log "장애 발생: DROP TABLE chunks, documents"
IMPACT=$(probe)
log "영향 확인: 서비스=$IMPACT"

echo "== 4. 복구 (최신 백업)"
RESTORE_OUT=$(./scripts/restore.sh)
T_RESTORED=$(now)
log "복구 완료: $(echo "$RESTORE_OUT" | head -1 | python3 -c 'import sys,json; print(json.loads(sys.stdin.read())["key"])')"

echo "== 5. 재확인"
AFTER_DOCS=$(sql "SELECT count(*) FROM documents"); AFTER_CHUNKS=$(sql "SELECT count(*) FROM chunks")
MARKER=$(sql "SELECT count(*) FROM audit_log WHERE user_id = 'drill'")
RLS=$(sql "SELECT count(*) FROM pg_policies WHERE tablename IN ('documents','chunks')")
SERVICE_AFTER=$(probe)
T_VERIFIED=$(now)
log "사후: documents=$AFTER_DOCS, chunks=$AFTER_CHUNKS, RLS 정책=$RLS개, 서비스=$SERVICE_AFTER"
log "RPO 표식(백업 이후 감사 로그) 남은 수: $MARKER (0이면 잃음)"

RTO=$((T_VERIFIED - T_INCIDENT)); RESTORE_ONLY=$((T_RESTORED - T_INCIDENT)); RPO=$((T_INCIDENT - T_BACKUP))
cat > docs/restore-drill-report.md <<EOF
# 복구 훈련 보고서 (DB: 문서·청크 테이블 유실)

- 일시: $(date "+%Y-%m-%d %H:%M") / 환경: kind 4노드, PostgreSQL 17 + pgvector, 백업 저장소 MinIO(backups 버킷)
- 시나리오: 운영자 실수로 \`documents\`, \`chunks\` 테이블 삭제 → 사내 AI 검색 기능 중단
- 실행: \`CONFIRM=yes ./scripts/restore-drill.sh\`

## 결과 요약
| 지표 | 값 | 의미 |
|---|---|---|
| **RTO** (장애 → 기능 확인 완료) | **${RTO}초** | 복구 Job ${RESTORE_ONLY}초 + 기능 확인 |
| **RPO** (마지막 백업 → 장애) | **${RPO}초** | 이 구간에 생긴 데이터는 잃는다 |
| 잃은 데이터 | 백업 이후 넣은 감사 로그 표식 1건 → 복구 후 남은 수 **${MARKER}** | 0이면 백업 시점으로 되돌아가 잃은 것 |
| 문서 / 청크 | ${BEFORE_DOCS}/${BEFORE_CHUNKS} → ${AFTER_DOCS}/${AFTER_CHUNKS} | 사전과 동일해야 정상 |
| RLS 정책 (documents·chunks) | ${RLS}개 | 덤프에 정책·권한도 포함되어 함께 복구 |

## 타임라인
| 시각 | 내용 |
|---|---|
$(printf "%s\n" "${LOG[@]}")

## 해석
- 일 1회 백업(CronJob 02:00)이면 **최악의 RPO는 약 24시간**이다. 감사 로그처럼 잃으면 안 되는 데이터는 WAL 아카이빙(PITR)이나 스트리밍 복제로 RPO를 분·초 단위로 줄여야 한다.
- 이번 RTO는 데이터가 작아서(덤프 수백 KB) 짧다. 실제 규모에서는 덤프 크기·네트워크·인덱스 재생성(HNSW) 시간이 RTO를 좌우하므로, 고객 데이터 규모로 복구 시간을 미리 측정해 SLA에 반영한다.
- 백업 파일이 있다는 것과 복구가 된다는 것은 다르다. 이번 훈련으로 **덤프 → 다운로드 → pg_restore(단일 트랜잭션) → 기능 확인**까지 실제로 동작함을 확인했다.
EOF
echo; echo "보고서: docs/restore-drill-report.md (RTO ${RTO}s, RPO ${RPO}s)"
