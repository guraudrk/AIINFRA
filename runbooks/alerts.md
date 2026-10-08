# 알람 대응 가이드 (runbook)

> 각 알람의 `runbook_url`이 이 문서의 해당 절을 가리킨다. 형식: **의미 → 먼저 볼 것 → 조치 → 에스컬레이션**
> 장애 시나리오별 상세 런북은 `runbooks/0N-*.md`(M8)에 있다.

## gpu-high-temperature
- **의미**: GPU 온도가 85℃를 1분 넘게 초과. 계속되면 클럭이 떨어지고(throttling) 심하면 GPU가 스스로 멈춘다.
- **먼저 볼 것**: 대시보드 "GPU 온도"와 "GPU 사용률" → 부하 때문인지 냉각 문제인지 구분. `nvidia-smi -q -d TEMPERATURE,PERFORMANCE`로 throttle 사유 확인.
- **조치**: 부하 때문이면 동시 요청 제한·레플리카 분산. 냉각 문제(팬, 랙 흡기 온도, 공조)면 BMC(iDRAC/iLO)에서 팬·센서 로그 확인 후 현장 점검 요청.
- **에스컬레이션**: 90℃ 이상 지속 → 해당 노드 cordon·drain 후 하드웨어 담당.

## gpu-memory-high
- **의미**: GPU 메모리 사용률 90% 초과. 새 요청이나 긴 컨텍스트에서 OOM이 날 수 있다.
- **먼저 볼 것**: 어떤 모델이 올라가 있는지(`ollama ps` / vLLM 로그), 동시 요청 수, 컨텍스트 길이.
- **조치**: 동시성·컨텍스트 상한 축소, 양자화 모델로 교체, 모델을 다른 GPU로 분리.

## gpu-xid-error
- **의미**: 드라이버가 GPU 오류(Xid)를 보고. **79** = GPU가 PCIe 버스에서 떨어짐, **48** = 이중 비트 ECC(메모리 손상), **31** = 메모리 페이지 폴트(주로 앱 버그).
- **먼저 볼 것**: `dmesg | grep -i xid`, `nvidia-smi -q -d ECC`, 해당 GPU의 Pod 상태.
- **조치**: 79·48은 하드웨어 문제 가능성이 높다 → 노드 cordon·drain, 재부팅 후에도 재발하면 GPU 교체(벤더 RMA). 31은 해당 워크로드 로그부터 확인.

## llm-ttft-high
- **의미**: 사용자가 첫 글자를 보기까지 p95가 5초 초과.
- **먼저 볼 것**: "처리 중 LLM 요청(대기열)", GPU 사용률, 프롬프트 길이(RAG 청크 수).
- **조치**: 대기열이면 레플리카 증설·동시성 조정, GPU 포화면 증설, 프롬프트가 길면 TOP_K·청크 크기 축소.

## llm-queue-backlog
- **의미**: 처리 중 LLM 호출이 동시 슬롯(4)을 넘어 대기열이 생김. TTFT 상승의 앞단 신호.
- **조치**: llm-serving 레플리카·GPU 증설, 게이트웨이 동시성 제한(초과 요청은 빠르게 "잠시 후 재시도" 응답).

## ingress-5xx-high
- **의미**: 입구(Traefik)에서 5xx 비율 2% 초과.
- **먼저 볼 것**: Traefik 접근 로그의 경로·백엔드, `kubectl -n ai-platform get pods`, 게이트웨이 로그(503 = DB·LLM 연결 문제).
- **조치**: 원인 백엔드 복구. 배포 직후라면 롤백(`helm rollback`).

## permission-denied-spike
- **의미**: 10분간 권한 거부가 10건 초과.
- **먼저 볼 것**: 감사 로그 `SELECT user_id, role, denied, count(*) FROM audit_log WHERE ts > now() - interval '30 min' GROUP BY 1,2,3;`
- **조치**: 한 사용자의 반복이면 업무상 필요한 권한인지 확인(권한 요청 절차 안내) 또는 악용 시도로 보고. 여러 사용자면 권한 설정·배포 변경을 의심.

## pod-restarting
- **의미**: 15분간 같은 Pod가 2회 넘게 재시작.
- **먼저 볼 것**: `kubectl describe pod` (Last State, Exit Code: 137=OOMKilled, 1=앱 오류, 143=SIGTERM), `kubectl logs --previous`.

## pvc-usage-high
- **의미**: PVC 사용률 80% 초과. (kind의 local-path 볼륨은 kubelet이 사용량을 보고하지 않아 이 환경에서는 수집되지 않는다)
- **조치**: 로그·임시 파일 정리, 보관 정책 확인, 볼륨 확장(StorageClass allowVolumeExpansion).

## backup-not-succeeded
- **의미**: DB 백업 CronJob이 24시간 넘게 성공하지 못함 → 장애 시 복구 시점(RPO)이 그만큼 늘어난다.
- **먼저 볼 것**: `kubectl -n ai-platform get cronjob pg-backup`, 최근 Job 로그, MinIO backups 버킷 용량.
- **조치**: 원인 해결 후 `make backup`으로 즉시 백업, 성공 확인.

## cronjob-failed
- **의미**: 배치(Job)가 실패. 예: RLS를 켠 뒤 수집 Job이 COPY 오류로 실패한 회귀(M4).
- **먼저 볼 것**: `kubectl -n ai-platform logs job/<이름>`.
- **조치**: 원인 수정 후 `kubectl create job --from=cronjob/<이름>`으로 재실행, 확인 후 실패 Job 삭제(알람 해제).
