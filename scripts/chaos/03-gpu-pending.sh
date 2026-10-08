#!/usr/bin/env bash
# 시나리오 3: LLM이 GPU 3개를 요청 (노드 용량 2개, 그나마 임베딩이 1개 사용 중)
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    helm_set --set llmServing.gpu=3
    sleep 20
    ticket "인프라팀: 성능 개선한다고 LLM에 GPU를 더 할당하는 변경을 배포했는데," \
           "그 뒤로 AI 서비스가 아예 응답이 없습니다. 서버(노드)는 다 정상이라고 나와요." ;;
  revert) helm_reset; kubectl -n "$NS" rollout status deploy/llm-serving --timeout=600s >/dev/null; echo "원복 완료" ;;
  *) usage ;;
esac
