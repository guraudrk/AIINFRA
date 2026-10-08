#!/usr/bin/env bash
# 시나리오 7: 앱 권한 필터가 꺼진 버전이 배포됨 (예: 디버깅용 설정이 운영에 섞여 들어감)
#   → 작업자가 품질팀 전용 문서를 받는가? 두 번째 방어선(DB RLS)이 막는가? 감사 로그로 추적 가능한가?
source "$(dirname "$0")/lib.sh"
case "${1:-}" in
  inject)
    helm_set --set axGateway.appFilterEnabled=false
    kubectl -n "$NS" rollout status deploy/ax-gateway --timeout=300s >/dev/null
    ask worker01 "프레스 3호기 성형 깊이 불량 원인과 고객 클레임 내용 알려줘" >/dev/null 2>&1 || true
    ticket "정보보안팀: 오늘 오전 배포 변경 목록에 '검색 필터 설정 변경' 항목이 있습니다." \
           "작업자 계정이 품질팀 전용 문서(불량·클레임)를 볼 수 있게 됐는지 확인하고," \
           "실제로 유출이 있었는지, 누가 무엇을 조회했는지 보고해 주세요." ;;
  revert) helm_reset; kubectl -n "$NS" rollout status deploy/ax-gateway --timeout=300s >/dev/null; echo "원복 완료" ;;
  *) usage ;;
esac
