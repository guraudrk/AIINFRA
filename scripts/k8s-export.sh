#!/usr/bin/env bash
# 쿠버네티스 설정 백업: Helm 릴리스 값·렌더링된 매니페스트 + 클러스터 객체 목록을 tar로 묶는다.
# - 설정 원본은 git(차트·values·vendor)에 있으므로, 여기서는 "지금 실제로 적용된 상태"를 보관한다.
# - Secret 값은 내보내지 않는다(평문 유출 위험). 운영에서는 Vault/External Secrets 등 비밀 관리 도구가 원본이다.
set -euo pipefail
cd "$(dirname "$0")/.."
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="backup/out/k8s-$TS"
mkdir -p "$OUT"
for rel in $(helm list -A -o json | python3 -c 'import sys,json; [print(r["namespace"] + "/" + r["name"]) for r in json.load(sys.stdin)]'); do
  ns=${rel%/*}; name=${rel#*/}
  helm get values "$name" -n "$ns" -o yaml > "$OUT/helm-$name-values.yaml"
  helm get manifest "$name" -n "$ns" > "$OUT/helm-$name-manifest.yaml"
done
kubectl get ns,deploy,sts,ds,cronjob,svc,ingress,networkpolicy,pvc,pv,certificate,clusterissuer -A -o wide > "$OUT/objects.txt" 2>/dev/null
kubectl get secrets -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,TYPE:.type,KEYS:.data --no-headers \
  | sed -E 's/map\[([^]]*)\]/[keys only]/' > "$OUT/secrets-inventory.txt"   # 이름·종류만, 값은 제외
tar -czf "$OUT.tar.gz" -C backup/out "k8s-$TS" && rm -rf "$OUT"
echo "[k8s-export] $OUT.tar.gz ($(du -h "$OUT.tar.gz" | cut -f1))"
