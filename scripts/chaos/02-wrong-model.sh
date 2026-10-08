#!/usr/bin/env bash
# 시나리오 2: 존재하지 않는 모델 이름으로 배포 (예: 모델 업그레이드 작업 중 오타)
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    helm_set --set llmServing.model=qwen2.5:3b-instruct-q8
    sleep 40
    ticket "관리자: 어젯밤 모델 업그레이드 작업이 있었는데, 오늘 아침부터 AI가 답을 못 합니다." \
           "작업자는 '배포는 성공(deployed)으로 끝났다'고 합니다." ;;
  revert) helm_reset; kubectl -n "$NS" rollout status deploy/llm-serving --timeout=600s >/dev/null; echo "원복 완료" ;;
  *) usage ;;
esac
