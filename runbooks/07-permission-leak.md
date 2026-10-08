# 07. 앱 권한 필터 비활성화 (보안 사고 조사)

> 재현: `make chaos SCENARIO=7` / 원복: `make chaos-revert SCENARIO=7`

## 증상
배포 변경 목록에 "검색 필터 설정 변경". 작업자 계정의 품질 문서 접근 여부 조사 요청.

## 영향
실제 유출 없음 (DB RLS가 차단)

## 확인 명령 (실제 출력 일부)
```bash
kubectl -n ai-platform get deploy ax-gateway -o yaml | grep -A1 FILTER    # APP_FILTER_ENABLED=false
SELECT ts, user_id, role, question, doc_ids, result FROM audit_log WHERE user_id='worker01' ORDER BY id DESC;
#   08:33:55 worker01 | 프레스 3호기 성형 깊이 불량 원인과 고객 클레임 | {} | unknown   <- 실제 출력
-- ax_app 계정 직접 조회: app.role=worker → quality 청크 0 / app.role=quality → 25
```

## 원인
디버깅용 설정(APP_FILTER_ENABLED=false)이 운영 배포에 포함

## 조치
설정 원복, 감사 로그로 해당 기간 전체 조회 이력 확인 후 보고 (docs/incident-report-sample.md)

## 재발 방지
- 보안 관련 설정은 배포 전 정책 검사 (values 검증, Admission 정책)
- 권한 테스트(make test)를 배포 파이프라인 필수 단계로
- PermissionDeniedSpike·이상 조회 알람
