#!/usr/bin/env bash
# 폐쇄망 반입 번들 생성 (인터넷이 되는 "사무실" 쪽에서 실행)
#   airgap/images/*.tar   컨테이너 이미지 (docker save)
#   airgap/models/*.tar   모델 파일 (서빙 Pod의 PVC에서 추출)
#   airgap/source.tar.gz  설치 소스(차트·스크립트·vendor 매니페스트·가상 데이터) = git HEAD
#   airgap/MANIFEST.txt, SHA256SUMS
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=airgap
NS=ai-platform
mkdir -p "$OUT/images" "$OUT/models"

# 1) 이미지 목록: 지금 클러스터에서 실제로 쓰는 이미지 + Job이 쓰는 이미지
#    kind 노드 이미지에 이미 들어 있는 쿠버네티스 핵심 이미지(apiserver, etcd 등)는 제외
kubectl get pods -A -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{range .spec.initContainers[*]}{.image}{"\n"}{end}{end}' \
  | sort -u \
  | grep -vE '^registry\.k8s\.io/(kube-apiserver|kube-controller-manager|kube-scheduler|kube-proxy|etcd|coredns|pause)|kindest/local-path' \
  | grep -vE "^$(helm get values ai-platform -n $NS -a -o json | python3 -c 'import sys,json; v=json.load(sys.stdin)["ingest"]["image"]; print(v.split(":")[0])'):" > "$OUT/images.txt" || true
# 현재 버전의 앱 이미지와 Job 전용 이미지를 명시적으로 추가
helm get values ai-platform -n $NS -a -o json | python3 -c '
import sys, json
v = json.load(sys.stdin)
for k in ("ingest", "axGateway", "webUi"):
    print(v[k]["image"])' >> "$OUT/images.txt"
echo "curlimages/curl:8.11.1" >> "$OUT/images.txt"      # 모델 적재 Job (온라인 설치용)
sort -u -o "$OUT/images.txt" "$OUT/images.txt"
echo "[bundle] 이미지 $(wc -l < "$OUT/images.txt")개"

# 2) 이미지 저장: 로컬에 없으면 pull 후 docker save
while read -r img; do
  file="$OUT/images/$(echo "$img" | tr '/:@' '___').tar"
  [[ -s "$file" ]] && { echo "  유지  $img"; continue; }
  docker image inspect "$img" >/dev/null 2>&1 || docker pull -q "$img" >/dev/null
  docker save -o "$file" "$img"
  echo "  저장  $img ($(du -h "$file" | cut -f1))"
done < "$OUT/images.txt"

# kind 노드 이미지 (클러스터 자체를 만드는 데 필요)
NODE_IMAGE=$(docker inspect ax-lab-control-plane --format '{{.Config.Image}}')
echo "$NODE_IMAGE" > "$OUT/node-image.txt"
[[ -s "$OUT/images/kind-node.tar" ]] || docker save -o "$OUT/images/kind-node.tar" "$NODE_IMAGE"

# 3) 모델: 서빙 Pod의 /root/.ollama/models 를 tar로 추출 (인터넷 다운로드 대신 반입)
for svc in llm-serving embedding-serving; do
  file="$OUT/models/$svc.tar"
  [[ -s "$file" ]] && { echo "  유지  모델 $svc"; continue; }
  kubectl -n $NS exec deploy/$svc -- tar -C /root/.ollama -cf - models > "$file"
  echo "  추출  모델 $svc ($(du -h "$file" | cut -f1))"
done

# 4) 설치 소스 (커밋된 상태 그대로)
git archive --format=tar.gz -o "$OUT/source.tar.gz" HEAD

# 5) 목록·체크섬: 현장에서 "받은 파일이 변조·손상되지 않았는지" 검증
{
  echo "AX Platform Lab 반입 번들 — 생성 $(date '+%Y-%m-%d %H:%M') / git $(git rev-parse --short HEAD)"
  echo "kind 노드 이미지: $NODE_IMAGE"
  echo "--- 이미지"; cat "$OUT/images.txt"
  echo "--- 모델"; helm get values ai-platform -n $NS -a -o json | python3 -c 'import sys,json; v=json.load(sys.stdin); print(v["llmServing"]["model"]); print(v["embeddingServing"]["model"])'
} > "$OUT/MANIFEST.txt"
(cd "$OUT" && find images models source.tar.gz -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
echo "[bundle] 완료: $(du -sh "$OUT" | cut -f1)  ($OUT/MANIFEST.txt, $OUT/SHA256SUMS)"
