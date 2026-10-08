# 9장. 장애 대응 방법론

> 관련: M8 · 노트 [08-troubleshooting](../study/08-troubleshooting.md) · [런북](../../runbooks/) · [보안 사고 보고서](../incident-report-sample.md)

## 9.1 증상에서 근본 원인으로: 진단 순서

**정의**: **증상**은 겉으로 보이는 현상(답이 안 온다), **근본 원인**은 그걸 만든 진짜 이유(메모리 상한을 잘못 줄인 배포)다. 증상만 없애면(재시작) 다시 난다.

**진단 순서 (넓은 곳 → 좁은 곳)**
1. **증상 구체화**: 무엇이 안 되나(전체/일부), 언제부터, 누구에게, 무엇은 되나(로그인은 됨 → 입구·인증은 정상)
2. **기능 경로로 번역**: 브라우저 → 입구 → 게이트웨이 → 임베딩 → DB → LLM
3. **상태 훑기**: `kubectl get pods`의 STATUS·READY·RESTARTS·**AGE**
4. **상세**: `describe`의 Last State(Exit Code, Reason), Events(스케줄링·probe 실패)
5. **로그**: `logs`, 재시작됐으면 `logs --previous`
6. **변경 이력과 시점 맞추기**: Helm history, 배포 기록 → "그 시각에 무엇이 바뀌었나"
7. 가설 → 검증 → 조치 → **원복·조치 결과까지 확인**

**흔한 함정 — "원래 있던 오류"**: M8 시나리오 1에서 처음에 63분 전에 생긴 수집 Job 오류를 원인으로 짚었다. **시점**(증상 시작과 맞는가)과 **경로**(고객 기능의 경로에 있는가)를 같이 보지 않아서다.

**면접 한 줄**: "증상을 기능 경로로 바꾸고, Pod 상태 → describe → 로그 → 변경 이력 순으로 좁히며, 항상 시점과 경로가 맞는지 확인합니다."

---

## 9.2 Pod 상태별 진단표

| 상태 | 의미 | 먼저 볼 것 | 이 프로젝트 사례 |
|---|---|---|---|
| **Pending** | 배치할 노드가 없음 | describe → `FailedScheduling` (자원 부족 / taint / selector / PVC) | GPU 3개 요청 → `Insufficient nvidia.com/gpu` |
| **ContainerCreating** (오래) | 이미지·볼륨 준비 중 | Events: 이미지 pull, 볼륨 마운트, Secret 없음 | 첫 배포 때 Ollama 이미지 3.8GB pull |
| **ImagePullBackOff** | 이미지를 못 받음 | 이미지 이름·태그, 레지스트리 접근, **폐쇄망 반입 누락** | digest 고정 MinIO 이미지 이름 문제(폐쇄망) |
| **Running + READY 0/1** | 살아 있지만 준비 검사 실패 | readiness probe 실패 메시지 | 없는 모델 이름 → `model not found` |
| **CrashLoopBackOff** | 죽고 재시작 반복(간격 증가) | `logs --previous`, Last State Exit Code | – |
| **Running, RESTARTS 증가** | 주기적으로 죽음 | Last State: OOMKilled / Error | LLM 메모리 512Mi → OOMKilled |
| **Running인데 느림** | 자원 압박 | `kubectl top`, CPU throttling, 대기열 지표 | Grafana CPU limit throttling |
| **Completed / Error (Job)** | 배치 종료 / 실패 | Job 로그, 재시도 여부 | 재부팅 직후 DNS 실패 → 재시도로 성공 |

---

## 9.3 종료 코드 (Exit Code)

| 코드 | 의미 | 원인 |
|---|---|---|
| 0 | 정상 종료 | Job 성공 |
| 1 | 앱 오류로 스스로 종료 | 설정 오류, 예외 → 로그 확인 |
| **137** | 128 + 9 (**SIGKILL**) | 대부분 **OOMKilled**(메모리 limit 초과로 커널이 강제 종료), 또는 강제 삭제 |
| **143** | 128 + 15 (**SIGTERM**) | 정상 종료 요청(배포·축소·노드 드레인). 유예 시간 안에 안 끝나면 이후 SIGKILL |

**원리**: 리눅스에서 신호로 종료된 프로세스의 종료 코드는 128 + 신호 번호다. SIGKILL(9)은 막거나 정리할 수 없는 즉시 종료, SIGTERM(15)은 정리할 기회를 주는 종료 요청이다.

**면접 한 줄**: "137은 SIGKILL로 대부분 OOMKilled, 143은 SIGTERM으로 정상 종료 요청, 1은 앱 오류입니다."

---

## 9.4 배포 성공 ≠ 서비스 정상

**원리**: `helm upgrade`(기본 대기 전략)는 쿠버네티스에 설정을 넣는 데 성공하면 `deployed`가 된다. 새 Pod가 실제로 Ready가 됐는지는 기다리지 않는다.

**이 프로젝트에서 두 번 겪음**
1. 시나리오 2: 없는 모델 이름으로 배포 → `deployed`인데 LLM READY 0/1.
2. 훈련 도구: 장애를 `--set`으로 넣은 뒤 값 없이 `helm upgrade`로 "원복"했는데, 직전에 덮어쓴 값이 다시 적용되어 **원복 배포 성공, 장애 설정은 그대로**였다 → `--reset-values` 명시 + 원복 후 실제 값 검증.

**대책**: `--wait`(watcher)와 `--rollback-on-failure`(Helm 3의 `--atomic`)로 준비 실패 시 자동 롤백, 배포 후 스모크 테스트(실제 질문 한 번), 권한 자동 테스트.

**면접 한 줄**: "배포 도구의 성공은 설정이 들어갔다는 뜻이지 서비스가 정상이라는 뜻이 아니라서, wait와 자동 롤백, 배포 후 확인을 붙입니다."

---

## 9.5 장애 보고서와 고객 커뮤니케이션

**장애 대응 흐름**: 접수 → 등급 판정(영향 범위·긴급도) → **고객 1차 공지**(인지했고 조사 중, 다음 공지 시각) → 진단 → **임시 조치(서비스 복구 우선)** → 근본 원인 → 영구 조치 → 보고서.

**장애 보고서 구성 (Postmortem)**: 요약, 타임라인, 영향 범위, 근본 원인(직접 원인 + 구조적 원인), 임시·영구 조치, 고객 공유 문구, 후속 과제. **사람을 탓하지 않고 구조를 고친다(blameless).**

**고객 커뮤니케이션 원칙**
- 확인된 사실 / 조사 중인 것 / 다음 공지 시각을 구분한다.
- 추측을 사실처럼 말하지 않는다.
- 기술 용어보다 **영향**(무엇이 안 되는지, 데이터는 안전한지)부터 말한다.
- 보안 사고는 "유출 없음"을 **증거(감사 로그, DB 검증)**로 말한다.

**이 프로젝트에서는**: 시나리오 7(앱 권한 필터 비활성화)을 실제 고객 보고서 형식으로 썼다. 감사 로그(작업자 질의 사용 문서 0건)와 앱 계정 직접 조회(작업자 0 / 품질 25)로 RLS가 막아 유출이 없음을 증명했다.

**지표**: MTTD(알아차리기까지 시간), MTTR(복구까지 시간). 알람이 MTTD를, 런북이 MTTR을 줄인다.

**면접 한 줄**: "장애 중에는 확인된 사실과 조사 중인 것을 구분해 정해진 주기로 알리고, 끝나면 사람이 아니라 구조를 고치는 보고서를 씁니다."

---

## 9.6 리눅스·하드웨어 점검 명령

| 영역 | 명령 | 보는 것 |
|---|---|---|
| 프로세스·자원 | `top`, `free -h`, `df -h`, `iostat` | CPU·메모리·디스크 포화 |
| 커널 로그 | `dmesg -T`, `journalctl -k` | OOM Killer, GPU Xid, 디스크 오류 |
| 서비스 | `systemctl status kubelet`, `journalctl -u kubelet` | 노드 에이전트 상태 |
| 네트워크 | `ip a`, `ip route`, `ss -tulnp`, `ping`, `traceroute`, `curl -v`, `dig` | 인터페이스, 경로, 포트 점유, DNS, TLS 단계 |
| GPU | `nvidia-smi`, `nvidia-smi -q -d PERFORMANCE`, `dcgmi diag` | 사용률·메모리·온도·throttle·진단 |
| 시간 | `timedatectl`, `chronyc tracking` | NTP 동기화 (인증서·로그 시각) |
| 하드웨어 | BMC(iDRAC/iLO) 이벤트 로그 | 전원·팬·온도·메모리 오류 |
