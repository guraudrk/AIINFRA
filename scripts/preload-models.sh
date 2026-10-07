#!/usr/bin/env bash
# 모델 사전 적재 Job: 각 Ollama 서버에 "이 모델을 받아 PVC에 저장해"라고 요청한다.
# - Job은 curl 클라이언트일 뿐이고, 실제 다운로드·저장은 서빙 Pod가 자기 PVC(/root/.ollama)에 한다.
# - 모델이 PVC에 들어가면 서빙 Pod의 readinessProbe(ollama show)가 통과해 Ready가 된다.
# - 폐쇄망(M5)에서는 이 단계를 "내부 저장소/반입 파일에서 PVC로 복사"로 바꾼다.
set -euo pipefail

NS="${NS:-ai-platform}"
LLM_MODEL=$(helm get values ai-platform -n "$NS" -a -o json | python3 -c 'import sys,json; print(json.load(sys.stdin)["llmServing"]["model"])')
EMB_MODEL=$(helm get values ai-platform -n "$NS" -a -o json | python3 -c 'import sys,json; print(json.load(sys.stdin)["embeddingServing"]["model"])')

preload() {
  local target=$1 model=$2
  kubectl -n "$NS" delete job "preload-$target" --ignore-not-found >/dev/null
  kubectl -n "$NS" apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: preload-$target
  labels:
    app.kubernetes.io/part-of: ai-platform
    app.kubernetes.io/component: model-preload
spec:
  backoffLimit: 3
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: pull
          image: curlimages/curl:8.11.1
          command: ["sh", "-c"]
          args:
            - |
              echo "[preload] $model → $target-admin"
              # 일반 Service($target)는 Ready Pod에만 연결된다. 모델이 없으면 Ready가 아니므로 관리용 -admin Service로 접속
              until curl -sf http://$target-admin:11434/ >/dev/null; do echo "서버 대기..."; sleep 5; done
              # stream=false: 다운로드가 끝날 때까지 기다렸다가 {"status":"success"} 한 줄을 받는다
              curl -sf -X POST http://$target-admin:11434/api/pull \
                -d '{"model":"$model","stream":false}' | tee /tmp/out
              grep -q '"success"' /tmp/out
EOF
}

preload llm-serving "$LLM_MODEL"
preload embedding-serving "$EMB_MODEL"

echo "[preload] 다운로드 완료 대기 (최대 30분)"
kubectl -n "$NS" wait --for=condition=complete job/preload-llm-serving job/preload-embedding-serving --timeout=1800s
kubectl -n "$NS" rollout status deploy/llm-serving --timeout=300s
kubectl -n "$NS" rollout status deploy/embedding-serving --timeout=300s
