# 06. 모니터링·알람 — GPU·LLM·서비스를 한 화면에서

## 한 줄 요약
kube-prometheus-stack으로 Prometheus·Grafana·Alertmanager를 올렸다. DCGM과 같은 이름의 GPU 지표 시뮬레이터, 게이트웨이의 TTFT·토큰/초·대기열 지표, DB·MinIO·입구 지표를 수집하고, 대시보드 2개와 알람 11종(심각도·runbook 링크 포함)을 만들었다. 부하와 과열 주입으로 **대기열 → TTFT 상승 → 알람**, **과열 → critical 알람**이 실제로 울리는 것을 확인했다.

## 용어 풀이 (비전공자용)
> 비유 기준: 클러스터 = 병원. 이번에는 **중앙 관제실**을 만들었다. 환자 모니터(지표) → 관제 화면(대시보드) → 비상벨(알람) → 대응 매뉴얼(runbook).

| 용어 | 쉬운 설명 | 비유 |
|---|---|---|
| **지표 (Metric)** | 시간에 따라 변하는 숫자(요청 수, 온도, 응답 시간). 이름 + 라벨 + 값 | 환자 모니터의 **심박수·체온** |
| **Prometheus** | 정해진 주기(15초)로 각 서비스의 `/metrics`를 가져가 저장하고, 알람 조건을 계산하는 시스템 | 15초마다 병실을 도는 **간호사 + 기록 차트** |
| **exporter** | 지표를 Prometheus가 읽을 수 있는 형식으로 내보내는 프로그램(node-exporter, postgres-exporter, dcgm-exporter) | 장비에 붙인 **측정 센서** |
| **scrape** | Prometheus가 지표를 가져가는 것(pull 방식) | 간호사의 **정기 회진** |
| **ServiceMonitor / PodMonitor** | "이 서비스의 이 포트에서 지표를 가져가라"는 수집 대상 정의. Operator가 Prometheus 설정으로 바꿔 준다 | 회진 **명단** |
| **PromQL** | Prometheus의 질의 언어. `rate`(초당 증가율), `histogram_quantile`(백분위), `sum by`(묶어서 합산) | 차트에서 숫자를 뽑는 **계산식** |
| **카운터 / 게이지 / 히스토그램** | 계속 증가하는 값(요청 수) / 오르내리는 값(온도, 대기열) / 값을 구간별로 센 것(응답 시간 분포 → p95 계산) | 누적 방문자 수 / 현재 체온 / **진료 시간 분포표** |
| **p95 (95 백분위)** | 100건 중 느린 5건을 뺀 최댓값. 평균보다 체감 품질을 잘 보여 준다 | 95%의 환자는 **이 시간 안에** 진료받음 |
| **Grafana** | 지표를 그래프와 표로 보여 주는 대시보드 도구 | **관제 화면** |
| **알람 규칙 (PrometheusRule)** | "이 조건이 이만큼 지속되면 알려라". `for: 1m`은 일시적 튐을 거르는 조건 | 체온 39℃가 **1분 넘게 지속되면** 비상벨 |
| **pending / firing** | 조건은 맞았지만 지속 시간을 기다리는 중 / 실제로 발생한 알람 | 비상벨 **대기 중 / 울림** |
| **Alertmanager** | 발생한 알람을 묶고, 중복을 줄이고, 메일·메신저·전화로 보낸다 | **당직 호출 시스템** |
| **severity** | critical(즉시 대응, 야간에도 호출) / warning(근무 시간 내 확인) | 응급 / 일반 진료 |
| **runbook** | 알람마다 "무엇을 보고 어떻게 조치할지" 적은 대응 매뉴얼 | **응급 처치 매뉴얼** |
| **4가지 황금 신호** | 지연(Latency), 트래픽(Traffic), 오류(Errors), 포화(Saturation). 서비스 모니터링의 기본 틀(Google SRE) | 환자 상태의 **4대 활력 징후** |
| **DCGM** | NVIDIA Data Center GPU Manager. GPU 사용률·메모리·온도·전력·Xid 오류를 수집하는 공식 도구(dcgm-exporter) | GPU 전용 **정밀 모니터** |
| **Xid** | NVIDIA 드라이버가 보고하는 GPU 오류 번호. 79 = 버스 이탈, 48 = 이중 비트 ECC(메모리 손상), 31 = 메모리 페이지 폴트 | GPU의 **고장 코드** |
| **TTFT / 대기열** | 첫 토큰까지 시간 / 처리 슬롯이 꽉 차서 기다리는 요청 | 첫마디까지 시간 / **대기실 인원** |
| **kube-state-metrics** | 쿠버네티스 객체 상태(Pod 재시작, CronJob 마지막 성공 시각 등)를 지표로 만든다 | 원무과의 **병상 현황판** |

## 핵심 개념
- **무엇을 볼지는 4가지 황금 신호로 정한다.** LLM 서비스에 맞추면 이렇다.
  - 지연: **TTFT** p95, 전체 응답 시간
  - 트래픽: 역할별 요청 수
  - 오류: 5xx 비율, 근거 0건 비율, 권한 거부
  - 포화: **대기열(처리 중 요청)**, GPU 사용률·메모리·온도
- **알람은 "사람이 행동해야 하는 것"만 건다.** 증상(사용자 영향: TTFT, 5xx) 중심으로 걸고, 원인 지표(GPU 온도, Xid)는 하드웨어 위험처럼 선제 조치가 필요한 것만 건다. 모든 알람에 심각도와 runbook이 있어야 새벽에 받은 사람이 바로 움직일 수 있다.
- **GPU는 일반 서버와 다른 고장이 있다.** 과열(throttling), 메모리 부족(OOM), Xid 오류(하드웨어·드라이버). `nvidia-smi`는 사람이 보는 도구이고, 클러스터 전체는 DCGM exporter → Prometheus로 본다.
- 비유: 병원 **중앙 관제실**이다. 모든 병실의 모니터(exporter)를 간호사(Prometheus)가 15초마다 기록하고, 관제 화면(Grafana)에 띄운다. 기준을 1분 넘게 벗어나면 비상벨(알람)이 울리고, 벨마다 붙은 매뉴얼(runbook)대로 대응한다.

## 이 프로젝트에서 내가 한 것
- **kube-prometheus-stack 92.1.0**(Prometheus Operator v0.94.1)을 monitoring 네임스페이스에 설치했다(차트는 infra/vendor에 고정). Grafana는 `https://localhost/grafana`(사내 CA 인증서), 관리자 비밀번호는 Secret에서 읽는다. kind에서 수집이 안 되는 etcd·scheduler·controller-manager 수집은 꺼서 거짓 알람을 막았다.
- **GPU 지표 시뮬레이터**(apps/gpu-sim-exporter): DCGM과 같은 지표 이름·라벨(`DCGM_FI_DEV_GPU_UTIL/TEMP/POWER_USAGE/FB_USED/FB_FREE/XID_ERRORS`)을 GPU 노드 DaemonSet으로 낸다. 사용률은 게이트웨이의 처리 중 LLM 요청 수를 따르고, 메모리는 Ollama에 올라간 모델 크기를 쓰고, 온도는 열관성을 흉내 내 천천히 변한다. `scripts/gpu-fault.sh overheat|xid79|clear`로 장애를 주입한다. 이름이 같으니 REAL 환경에서는 dcgm-exporter로 바꾸기만 하면 대시보드·알람을 그대로 쓴다.
- **게이트웨이 지표 보강**(0.1.3): 답변 생성을 스트리밍으로 바꿔 **TTFT 히스토그램**, Ollama 응답의 eval_count/eval_duration으로 **토큰/초**, **처리 중 LLM 호출 수(대기열)** 게이지를 추가했다.
- **수집 대상 5종 모두 up=1**: ax-gateway, gpu-sim-exporter, postgres-exporter(모니터링 전용 DB 계정 `ax_monitor`, pg_monitor 권한만), MinIO, Traefik(PodMonitor) + 기본 node-exporter, kube-state-metrics.
- NetworkPolicy가 기본 거부라 **monitoring 네임스페이스에서 각 지표 포트로 오는 길**과 시뮬레이터가 게이트웨이·LLM을 조회하는 길만 추가로 열었다.
- **대시보드 2개**(`scripts/gen_dashboards.py`로 생성, ConfigMap 라벨로 자동 등록)
  - AI 플랫폼: GPU 사용률·온도·메모리·전력·Xid, 대기열, TTFT p50/p95, 토큰/초, LLM 호출 시간, 노드 CPU·메모리
  - 서비스 운영: 역할별 요청, 권한 거부, 근거 0건 비율, 응답 결과, 입구 5xx, 응답 시간 p95, DB 연결, PVC, 마지막 백업, 발생 중 알람, Pod 재시작
- **알람 11종** (모두 severity + runbook_url → `runbooks/alerts.md`): GPU 온도 > 85℃, GPU 메모리 > 90%, Xid, TTFT p95 > 5초, 대기열 > 4, 입구 5xx > 2%, 권한 거부 급증, Pod 재시작, PVC > 80%, 백업 24시간 미성공(kube-state-metrics의 CronJob 마지막 성공 시각 활용), **Job 실패**(M4 회귀 경험으로 추가)
- **실제로 울려 봤다**
  1. 게이트웨이에 동시 질문 6개 → 처리 중 5건 → `LLMQueueBacklog` **firing**, 그 여파로 TTFT p95가 1분까지 늘어 `LLMTTFTHigh` pending. "대기열이 생기면 TTFT가 튄다"를 지표로 확인했다.
  2. 과열 주입 → GPU 0 온도 92℃ → 1분 뒤 `GPUHighTemperature` **critical firing** → 해제.
- **겪은 문제**
  1. Grafana를 `/grafana` 하위 경로로 옮기자 Grafana 자체 지표 주소도 `/grafana/metrics`로 바뀌어 `TargetDown`이 떴다. ServiceMonitor 경로를 고쳤다.
  2. `prom-query.sh` 안 Python의 따옴표 이스케이프 오류, 장애 주입 명령이 port-forward보다 먼저 실행된 순서 실수 → 스크립트로 만들어 재사용했다(`prom-query.sh`, `gpu-fault.sh`).
  3. **Grafana 대시보드 목록이 몇 분째 로딩만 됨**: Pod가 2/3 NotReady, 로그에 `Handler timeout`, 검색 API 503이었다. `kubectl top`으로 보니 Grafana CPU가 **limit 500m에 딱 붙어** 있었다(CPU throttling). limit을 1500m으로 올리자 새 Pod가 636m을 쓰며 API가 0.02초에 200을 돌려줬다. 교훈: **메모리 limit 초과는 OOMKilled로 죽어서 눈에 띄지만, CPU limit 초과는 죽지 않고 조용히 느려진다.** limit은 실측 사용량을 보고 정한다.
  4. 재부팅 직후 수집 CronJob이 DNS 실패로 한 번 실패했지만 Job 재시도(backoffLimit)로 성공했다. 기동 순서 문제는 재시도로 흡수할 수 있다.
- **이 환경의 한계**: kind의 local-path 볼륨은 kubelet이 사용량을 보고하지 않아 PVC 지표가 비어 있다. NTP가 없어 `NodeClockNotSynchronising`가 뜬다. CPU가 추론으로 포화되면 `PrometheusMissingRuleEvaluations`가 뜬다.

## 실제 기업 환경에서는
- **GPU 모니터링은 GPU Operator의 dcgm-exporter**를 쓰고, 하드웨어(팬, PSU, 온도 센서)는 **BMC(iDRAC/iLO)의 Redfish/SNMP**로 따로 수집한다. Xid는 노드의 커널 로그(dmesg)에도 남아서, 로그 수집(Loki, ELK)과 같이 본다.
- Prometheus는 보관 기간이 짧아서 장기 저장은 Thanos·Mimir·VictoriaMetrics를 붙인다. 대규모·다중 클러스터는 수집과 저장을 분리한다.
- 알람은 Alertmanager에서 사내 메신저·메일·온콜 도구(PagerDuty 등)로 보내고, 같은 원인 알람은 묶는다(inhibit: 노드 다운이면 그 노드 Pod 알람은 억제). 고객사 운영 SLA(예: critical 30분 내 응답)와 연결한다.
- LLM 서비스는 vLLM이 TTFT·대기열·KV 캐시 사용률 지표를 직접 내보내서(`vllm:time_to_first_token_seconds`, `vllm:num_requests_waiting`, `vllm:gpu_cache_usage_perc`) 이번처럼 게이트웨이에서 따로 잴 필요가 줄어든다.
- 폐쇄망 고객은 Grafana 플러그인·대시보드도 반입 대상이고, NTP·DNS를 내부에 둬야 인증서·로그 시각이 맞는다.

## 에티버스그룹 사업과의 연결
이테크시스템의 통합 구축 범위에 **모니터링과 유지보수**가 들어 있다. 구축 후 고객이 가장 먼저 묻는 건 "GPU가 제대로 일하고 있나, 사용자가 불편하지 않나"이다. GPU 지표(DCGM)와 사용자 체감 지표(TTFT, 5xx)를 한 화면에 묶고, 알람마다 대응 매뉴얼을 붙여 두는 것이 유지보수 계약의 실체라고 생각한다.

## 자주 쓰는 명령어
```bash
./scripts/prom-query.sh 'up{namespace="ai-platform"}'          # PromQL 즉석 조회
./scripts/prom-query.sh --alerts                                # pending/firing 알람
./scripts/gpu-fault.sh overheat | xid79 | clear                 # GPU 장애 주입
kubectl -n monitoring get prometheus,alertmanager,servicemonitor -A
kubectl -n ai-platform get servicemonitor,podmonitor,prometheusrule
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus 9090   # Prometheus UI → Status > Targets
kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo
# 실제 GPU 서버
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu,power.draw --format=csv -l 5
nvidia-smi -q -d PERFORMANCE        # throttle 사유
dmesg | grep -i xid                 # Xid 오류
dcgmi diag -r 2                     # DCGM 진단
```

### 자주 쓰는 PromQL
```promql
rate(ax_requests_total[5m])                                             # 초당 요청 (카운터는 rate로)
histogram_quantile(0.95, sum by (le) (rate(ax_llm_ttft_seconds_bucket[5m])))   # TTFT p95
sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) / sum(rate(traefik_service_requests_total[5m]))  # 5xx 비율
DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)       # GPU 메모리 사용률
time() - kube_cronjob_status_last_successful_time{cronjob="pg-backup"}  # 마지막 백업 후 경과 초
```

## 예상 면접 질문 5개 + 모범 답변

**Q1. AI 서비스에서 무엇을 모니터링해야 하나요?**
> 4가지 황금 신호에 맞춰 나눴습니다. 지연은 첫 토큰까지 시간인 TTFT의 p95, 트래픽은 역할별 요청 수, 오류는 5xx 비율과 근거를 못 찾은 비율, 포화는 LLM 대기열과 GPU 사용률, 메모리, 온도입니다. 실제로 동시 요청을 6개 보내 봤더니 슬롯이 4개라 대기열이 생기고, 바로 TTFT p95가 1분까지 늘어나는 게 대시보드에 그대로 보였습니다. 그래서 TTFT 알람만 있으면 늦고, 대기열 알람이 앞단의 신호 역할을 한다고 판단했습니다.

**Q2. Prometheus는 어떻게 동작하나요? rate와 histogram_quantile은 왜 쓰나요?**
> Prometheus는 각 서비스의 /metrics를 15초마다 가져가서 저장하는 pull 방식입니다. 요청 수 같은 카운터는 계속 커지기만 해서 값 자체는 의미가 없고, rate로 초당 증가율을 봐야 합니다. 응답 시간은 히스토그램으로 구간별 개수를 모아 두고, histogram_quantile로 p95 같은 백분위를 계산합니다. 평균은 느린 소수 요청을 가려 버려서 사용자 체감은 p95로 보는 게 맞다고 생각합니다. 쿠버네티스에서는 ServiceMonitor라는 정의를 만들면 Operator가 수집 설정을 자동으로 만들어 줍니다.

**Q3. GPU 장애는 어떻게 감지하나요? Xid는 뭔가요?**
> NVIDIA DCGM exporter로 사용률, 메모리, 온도, 전력, Xid를 수집합니다. Xid는 드라이버가 보고하는 GPU 오류 번호인데, 79는 GPU가 PCIe 버스에서 떨어진 것, 48은 이중 비트 ECC로 메모리가 손상된 것이라 하드웨어 문제 가능성이 높고, 31은 메모리 페이지 폴트라 주로 애플리케이션 쪽 문제입니다. 제 PC에는 쿠버네티스에 붙은 GPU가 없어서 DCGM과 같은 지표 이름을 내는 시뮬레이터를 만들었고, 과열을 주입해서 85도 알람이 1분 뒤 critical로 울리는 것까지 확인했습니다. 지표 이름이 같아서 실제 서버에서는 exporter만 바꾸면 됩니다.

**Q4. 알람은 어떻게 설계하나요? 알람이 너무 많으면요?**
> 사람이 행동해야 하는 것만 걸고, 모든 알람에 심각도와 대응 문서 링크를 붙였습니다. critical은 즉시 대응, warning은 근무 시간 내 확인입니다. 일시적으로 튀는 값은 "1분 이상 지속" 같은 조건으로 거르고요. 알람이 많으면 다들 무시하게 되니까, 같은 원인의 알람은 Alertmanager에서 묶거나 억제하고, 오탐이 나는 건 바로 고쳐야 합니다. 실제로 Grafana 경로를 바꾸면서 생긴 TargetDown이나 kind에서 수집이 안 되는 구성요소 알람을 정리했습니다. 그리고 수집 배치가 깨졌던 경험이 있어서 Job 실패 알람을 추가했습니다.

**Q5. 대시보드를 만들 때 무엇을 기준으로 구성했나요?**
> 보는 사람이 다르다고 보고 두 개로 나눴습니다. 인프라 엔지니어용은 GPU 사용률, 온도, 메모리, Xid와 LLM 대기열, TTFT, 노드 자원이고, 서비스 운영용은 역할별 요청, 권한 거부, 근거 0건 비율, 5xx, DB 연결, 마지막 백업 시각입니다. 패널마다 알람 기준선을 같이 그려서 지금 얼마나 여유가 있는지 바로 보이게 했습니다. 대시보드는 코드로 생성해서 차트와 함께 배포되니까, 고객사에 설치할 때도 똑같이 들어갑니다.

## 꼬리 질문 3개 + 답변 방향
1. **"Prometheus 데이터는 얼마나 보관하나요?"** → 이번에는 로컬 3일. 운영은 15~30일을 로컬에 두고 장기 저장은 Thanos·Mimir 등으로 오브젝트 스토리지(MinIO)에 보낸다. 용량은 시계열 수 × 수집 주기 × 보관 기간으로 추정한다.
2. **"모니터링 시스템이 죽으면요?"** → 알람이 안 오니 장애를 모른다. 그래서 Watchdog(항상 울리는 알람)이 끊기면 외부에서 알려 주는 데드맨 스위치를 두고, 모니터링 스택도 HA로 구성한다(Prometheus 2대, Alertmanager 3대).
3. **"pull 방식이면 짧게 끝나는 배치 작업 지표는요?"** → 수집 주기 사이에 끝나서 못 가져간다. Pushgateway를 쓰거나, 이번처럼 kube-state-metrics의 Job·CronJob 상태(마지막 성공 시각)를 쓴다. 백업 감시는 후자로 했다.
