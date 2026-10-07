#!/usr/bin/env bash
# NetworkPolicy 검증: 실제 Pod 안에서 TCP 연결을 시도해 허용/차단을 기대값과 비교한다.
#   ./scripts/netpol-test.sh        (정책 적용 전에 돌리면 "전부 열려 있음"을 볼 수 있다)
set -uo pipefail
NS="${NS:-ai-platform}"
PROBE=netpol-probe   # 라벨 없는 "외부인" Pod: 아무 정책에도 허용되지 않은 상태

kubectl -n "$NS" get pod "$PROBE" >/dev/null 2>&1 || {
  kubectl -n "$NS" run "$PROBE" --image=busybox:1.36 --restart=Never --labels=role=netpol-probe -- sleep 3600 >/dev/null
  kubectl -n "$NS" wait --for=condition=Ready "pod/$PROBE" --timeout=60s >/dev/null
}

# 연결 시도 함수: 출발 Pod 종류별로 쓸 수 있는 도구가 다르다
try_conn() {   # $1=출발 $2=host $3=port → open/blocked
  local src=$1 host=$2 port=$3 out
  case $src in
    ax-gateway)  # python 이미지
      out=$(kubectl -n "$NS" exec deploy/ax-gateway -- python -c "
import socket,sys
try: socket.create_connection(('$host',$port),timeout=3); print('open')
except Exception as e: print('blocked')" 2>/dev/null) ;;
    web-ui)      # alpine(busybox nc)
      out=$(kubectl -n "$NS" exec deploy/web-ui -- sh -c "nc -z -w 3 $host $port && echo open || echo blocked" 2>/dev/null) ;;
    probe)       # busybox
      out=$(kubectl -n "$NS" exec "$PROBE" -- sh -c "nc -z -w 3 $host $port && echo open || echo blocked" 2>/dev/null) ;;
  esac
  echo "${out:-blocked}"
}

dns_ok() {  # 외부인 Pod도 DNS 조회는 되어야 한다 (DNS만 허용 정책)
  # busybox nslookup은 검색 도메인 중 마지막 실패를 종료 코드로 남기므로 전체 이름(FQDN)으로 묻는다
  kubectl -n "$NS" exec "$PROBE" -- nslookup "postgres.$NS.svc.cluster.local" >/dev/null 2>&1 && echo open || echo blocked
}

# 출발 | 목적지 | 포트 | 기대값 | 설명
CASES=(
  "web-ui|ax-gateway|8000|open|채팅 화면 → 게이트웨이"
  "web-ui|postgres|5432|blocked|채팅 화면이 DB에 직접 접근"
  "web-ui|llm-serving|11434|blocked|채팅 화면이 LLM에 직접 접근"
  "ax-gateway|postgres|5432|open|게이트웨이 → DB"
  "ax-gateway|llm-serving|11434|open|게이트웨이 → LLM"
  "ax-gateway|embedding-serving|11434|open|게이트웨이 → 임베딩"
  "ax-gateway|minio|9000|blocked|게이트웨이는 MinIO를 쓰지 않음(최소 권한)"
  "ax-gateway|1.1.1.1|443|blocked|게이트웨이 → 외부 인터넷"
  "probe|postgres|5432|blocked|외부인 Pod → DB"
  "probe|ax-gateway|8000|blocked|외부인 Pod → 게이트웨이(입구 우회)"
  "probe|minio|9000|blocked|외부인 Pod → MinIO"
  "probe|1.1.1.1|443|blocked|외부인 Pod → 외부 인터넷"
)

pass=0; fail=0
printf "| 출발 | 목적지 | 기대 | 실제 | 판정 | 설명 |\n|---|---|---|---|---|---|\n"
for c in "${CASES[@]}"; do
  IFS='|' read -r src host port expect desc <<<"$c"
  actual=$(try_conn "$src" "$host" "$port")
  if [[ "$actual" == "$expect" ]]; then mark="✅"; pass=$((pass+1)); else mark="❌"; fail=$((fail+1)); fi
  printf "| %s | %s:%s | %s | %s | %s | %s |\n" "$src" "$host" "$port" "$expect" "$actual" "$mark" "$desc"
done
actual=$(dns_ok); expect=open
[[ "$actual" == "$expect" ]] && { mark="✅"; pass=$((pass+1)); } || { mark="❌"; fail=$((fail+1)); }
printf "| probe | kube-dns:53 | %s | %s | %s | DNS는 허용 |\n" "$expect" "$actual" "$mark"

# 외부 → 입구(Ingress)
code=$(curl -s -o /dev/null -w "%{http_code}" --cacert infra/tls/hanbit-root-ca.crt https://localhost/ 2>/dev/null || true)
[[ "$code" == "200" ]] && { mark="✅"; pass=$((pass+1)); } || { mark="❌"; fail=$((fail+1)); }
printf "| (PC 브라우저) | https://localhost/ | 200 | %s | %s | 입구를 통한 정상 접속 |\n" "$code" "$mark"

echo; echo "결과: 통과 $pass / 실패 $fail"
[[ $fail -eq 0 ]]
