#!/usr/bin/env bash
# 시나리오 1: LLM 서빙 메모리 limit을 모델보다 작게 → 모델 로딩 시 OOMKilled(Exit 137) 반복
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    helm_set --set llmServing.resources.limits.memory=512Mi --set llmServing.resources.requests.memory=256Mi
    kubectl -n "$NS" rollout status deploy/llm-serving --timeout=300s >/dev/null || true
    ask maint01 "3호기 E-203 대응 방법 알려줘" >/dev/null 2>&1 || true   # 모델 로딩 유발
    ticket "설비보전팀: 오늘 오후부터 AI 어시스턴트에 질문하면 한참 기다리다 오류가 납니다." \
           "로그인과 화면은 정상이에요. 어제까지는 잘 됐습니다." ;;
  revert) helm_reset; kubectl -n "$NS" rollout status deploy/llm-serving --timeout=600s >/dev/null; echo "원복 완료" ;;
  *) usage ;;
esac
