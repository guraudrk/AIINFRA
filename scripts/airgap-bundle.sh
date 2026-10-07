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

# 공개 이미지만 받으므로 로그인 정보가 필요 없다. WSL의 Docker CLI는 기본 설정(credsStore: desktop.exe)
# 때문에 pull마다 Windows 자격 증명 도우미를 호출하는데, WSL interop(vsock) 시간 초과로 간헐 실패한다.
# → 이 스크립트에서만 빈 설정 폴더를 써서 익명으로 받는다 (PC 전체 설정은 그대로).
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
echo '{}' > "$DOCKER_CONFIG/config.json"
trap 'rm -rf "$DOCKER_CONFIG"' EXIT

# 1) 이미지 목록: 설치 파일(차트·vendor 매니페스트)을 렌더링해서 image: 줄을 뽑는다.
#    → 클러스터가 없어도 같은 목록이 나오고, "설치 파일에 적힌 이미지 = 반입 목록"이 보장된다.
{
  helm template ai-platform charts/ai-platform
  helm template traefik infra/vendor/traefik-41.6.1.tgz -f infra/traefik-values.yaml
  cat infra/vendor/calico-v3.33.0.yaml infra/vendor/cert-manager-v1.21.2.yaml infra/vendor/metrics-server-v0.9.0.yaml
} | grep -E '^\s*-?\s*image:' | sed -E 's/.*image:\s*"?([^" ]+)"?.*/\1/' > "$OUT/images.txt"
cat >> "$OUT/images.txt" <<'EOF'
busybox:1.36
curlimages/curl:8.11.1
EOF
# busybox: NetworkPolicy 검증 Pod / curl: 모델 적재 Job(온라인 설치 경로)
sort -u -o "$OUT/images.txt" "$OUT/images.txt"
echo "[bundle] 이미지 $(wc -l < "$OUT/images.txt")개"

# 2) 이미지 저장: 로컬에 없으면 pull 후 docker save
#    digest로만 지정한 이미지(repo@sha256:...)는 태그가 없어 tar에 이름이 남지 않고, docker save가 목차를
#    다시 만들어 digest도 바뀐다 → 고정 태그 "pinned-<digest 8자리>"를 붙여 저장하고 대응표를 남긴다.
#    (실제 현장은 내부 레지스트리에 push하면 digest가 보존되어 이 우회가 필요 없다)
: > "$OUT/image-aliases.txt"
while read -r img; do
  ref="$img"
  if [[ "$img" == *@sha256:* ]]; then
    digest=${img#*@sha256:}
    ref="${img%@*}:pinned-${digest:0:8}"
    echo "$img $ref" >> "$OUT/image-aliases.txt"
  fi
  file="$OUT/images/$(echo "$ref" | tr '/:@' '___').tar"
  [[ -s "$file" ]] && { echo "  유지  $ref"; continue; }
  docker image inspect "$img" >/dev/null 2>&1 || docker pull -q "$img" >/dev/null
  [[ "$ref" != "$img" ]] && docker tag "$img" "$ref"
  # --platform: 멀티 아키텍처 이미지는 목차(index)에 arm64 등도 적혀 있는데 내용물은 amd64만 있다.
  # 목차째 저장하면 kind(ctr import --all-platforms)가 없는 플랫폼 내용을 찾다 실패한다 → 노드 플랫폼만 저장.
  docker save --platform linux/amd64 -o "$file" "$ref"
  echo "  저장  $ref ($(du -h "$file" | cut -f1))"
done < "$OUT/images.txt"

# kind 노드 이미지 (클러스터 자체를 만드는 데 필요). 이미 기록돼 있으면 그대로 쓴다
[[ -s "$OUT/node-image.txt" ]] || docker inspect ax-lab-control-plane --format '{{.Config.Image}}' > "$OUT/node-image.txt"
NODE_IMAGE=$(cat "$OUT/node-image.txt")
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
  echo "--- 모델"; helm template ai-platform charts/ai-platform | grep -A1 'name: MODEL_NAME' | grep value | sed -E 's/.*value: "?([^"]+)"?/\1/'
} > "$OUT/MANIFEST.txt"
(cd "$OUT" && find images models source.tar.gz -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
echo "[bundle] 완료: $(du -sh "$OUT" | cut -f1)  ($OUT/MANIFEST.txt, $OUT/SHA256SUMS)"
