#!/usr/bin/env bash
# 시나리오 5: 질문 임베딩 모델만 다른 모델로 교체 (문서는 재수집하지 않음) → 차원 불일치
#   문서 청크: bge-m3 1024차원 / 질문: qwen2.5:3b 임베딩 2048차원
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    helm_set --set axGateway.embedUrlOverride=http://llm-serving:11434 --set axGateway.embedModelOverride=qwen2.5:3b
    kubectl -n "$NS" rollout status deploy/ax-gateway --timeout=300s >/dev/null
    ticket "품질팀: 검색 품질 개선을 위해 임베딩 모델을 바꿨다고 들었는데, 그 뒤로 모든 질문이 오류입니다." ;;
  revert) helm_reset; kubectl -n "$NS" rollout status deploy/ax-gateway --timeout=300s >/dev/null; echo "원복 완료" ;;
  *) usage ;;
esac
