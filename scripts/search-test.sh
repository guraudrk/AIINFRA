#!/usr/bin/env bash
# 유사도 검색 확인: 질의문을 임베딩한 뒤 psql로 코사인 거리가 가까운 청크 상위 N개를 조회한다.
#   ./scripts/search-test.sh "E-203" 3
set -euo pipefail
NS="${NS:-ai-platform}"
QUERY="${1:-E-203}"
TOP="${2:-3}"

# 임베딩 서빙에 질의문 임베딩 요청 (port-forward로 잠깐 연결)
PORT=11499
kubectl -n "$NS" port-forward svc/embedding-serving "$PORT":11434 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null' EXIT
sleep 2
BODY=$(python3 -c 'import json,sys; print(json.dumps({"model": "bge-m3", "input": sys.argv[1]}))' "$QUERY")
VEC=$(curl -sf "http://localhost:$PORT/api/embed" -d "$BODY" \
  | python3 -c 'import sys,json; print("[" + ",".join(map(str, json.load(sys.stdin)["embeddings"][0])) + "]")')

echo "질의: \"$QUERY\" → 상위 $TOP개 (거리가 작을수록 유사, 1 - 거리 = 코사인 유사도)"
kubectl -n "$NS" exec -i postgres-0 -- psql -U postgres -d hanbit -v vec="$VEC" -v top="$TOP" <<'SQL'
SELECT c.doc_id, d.version, c.access_level, c.section,
       round((c.embedding <=> :'vec'::vector)::numeric, 4) AS distance
FROM chunks c JOIN documents d USING (doc_id)
ORDER BY c.embedding <=> :'vec'::vector
LIMIT :top;
SQL
