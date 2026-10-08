#!/usr/bin/env bash
# 시나리오 8: 문서·청크 테이블 삭제 → 백업 복구 (M7 복구 훈련 스크립트를 그대로 사용)
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject) CONFIRM=yes ./scripts/restore-drill.sh ;;
  revert) echo "복구 훈련 스크립트가 복구까지 수행함 (docs/restore-drill-report.md)" ;;
  *) usage ;;
esac
