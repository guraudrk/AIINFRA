# 7장. 관측성: 지표, Prometheus, 알람, GPU 모니터링

> 관련: M6 · 노트 [06-observability](../study/06-observability.md) · [알람 대응 가이드](../../runbooks/alerts.md)

## 7.1 관측성의 세 기둥과 황금 신호

**정의**: 관측성(Observability)은 시스템 밖에서 보이는 정보로 **안에서 무슨 일이 일어나는지 알아낼 수 있는 정도**다. 세 기둥이 있다.
| 기둥 | 무엇 | 도구 예 | 강점 |
|---|---|---|---|
| **지표 (Metrics)** | 시간에 따른 숫자 | Prometheus | 추세·알람, 저장 비용 작음 |
| **로그 (Logs)** | 사건 기록 문장 | Loki, ELK | 상세 원인 |
| **추적 (Traces)** | 요청 하나가 거친 경로와 구간별 시간 | Jaeger, Tempo | 어디서 느려졌는지 |

**4가지 황금 신호 (Google SRE)**: 지연(Latency), 트래픽(Traffic), 오류(Errors), 포화(Saturation). LLM 서비스에 대응시키면 지연 = **TTFT** p95, 트래픽 = 역할별 요청, 오류 = 5xx·근거 0건 비율, 포화 = **대기열·GPU 사용률·메모리**.

**면접 한 줄**: "지표로 추세와 알람을, 로그로 원인을 보고, 무엇을 볼지는 지연·트래픽·오류·포화 네 가지 황금 신호로 정합니다."

---

## 7.2 Prometheus의 동작

**정의**: Prometheus는 대상들의 `/metrics` 주소를 **주기적으로 가져와(pull, scrape)** 시계열로 저장하고, 질의(PromQL)와 알람 규칙 평가를 하는 시스템이다.

**동작 원리**
1. **exporter**나 앱이 `/metrics`에 텍스트로 지표를 내놓는다: `이름{라벨} 값`.
2. Prometheus가 15초마다 가져와 **시계열**(이름 + 라벨 조합마다 하나)로 저장한다.
3. **알람 규칙**을 주기적으로 평가해, 조건이 `for` 기간 동안 유지되면 **pending → firing**으로 바꾸고 Alertmanager에 보낸다.
4. Alertmanager가 묶고(grouping), 억제하고(inhibition), 메일·메신저로 보낸다.

**쿠버네티스에서 — Prometheus Operator**: ServiceMonitor/PodMonitor("이 서비스의 이 포트를 수집하라"), PrometheusRule(알람 규칙)을 쿠버네티스 객체로 만들면 Operator가 Prometheus 설정으로 바꿔 준다. kube-prometheus-stack은 Prometheus·Grafana·Alertmanager·kube-state-metrics·node-exporter를 한 번에 설치한다.

**지표 타입**
| 타입 | 의미 | 예 | 사용법 |
|---|---|---|---|
| Counter | 계속 증가 | 요청 수 | `rate()`로 초당 증가율 |
| Gauge | 오르내림 | 온도, 대기열 | 값 그대로 |
| Histogram | 값의 구간별 개수 | 응답 시간 | `histogram_quantile()`로 백분위 |

**pull 방식의 한계**: 수집 주기 사이에 끝나는 짧은 배치 작업은 못 가져간다 → Pushgateway, 또는 이 프로젝트처럼 **kube-state-metrics의 CronJob 마지막 성공 시각**으로 백업을 감시한다.

**면접 한 줄**: "Prometheus는 /metrics를 주기적으로 가져오는 pull 방식이고, 카운터는 rate로, 히스토그램은 histogram_quantile로 백분위를 계산합니다."

---

## 7.3 PromQL 핵심

```promql
rate(ax_requests_total[5m])
# 최근 5분 동안 카운터가 초당 얼마나 늘었나 (카운터 값 자체는 의미 없음)

sum by (role) (rate(ax_requests_total[5m]))
# 역할별로 묶어 합산

histogram_quantile(0.95, sum by (le) (rate(ax_llm_ttft_seconds_bucket[5m])))
# TTFT p95: 구간(le)별 개수 분포에서 95번째 백분위 위치를 보간

DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)
# GPU 메모리 사용률

time() - kube_cronjob_status_last_successful_time{cronjob="pg-backup"}
# 마지막 백업 성공 후 경과 초
```

**흔한 오해**: "평균 응답 시간이 짧으면 괜찮다" → 평균은 느린 소수 요청을 숨긴다. 사용자 체감은 p95·p99로 본다.

---

## 7.4 알람 설계

**원칙**
1. **사람이 행동해야 하는 것만** 건다. 울려도 할 일이 없는 알람은 피로만 만들고 결국 무시된다.
2. **증상 중심**: 사용자 영향(TTFT, 5xx)을 우선하고, 원인 지표는 선제 조치가 필요한 것(GPU 과열, Xid, 백업 미성공)만.
3. 일시적 튐은 `for: 1m` 같은 지속 조건으로 거른다.
4. 모든 알람에 **심각도**(critical = 즉시, warning = 근무 시간 내)와 **runbook 링크**.

**이 프로젝트의 11종**: GPU 온도 > 85℃, GPU 메모리 > 90%, Xid, TTFT p95 > 5초, 대기열 > 4, 입구 5xx > 2%, 권한 거부 급증, Pod 재시작, PVC > 80%, 백업 24시간 미성공, Job 실패(M4 회귀 경험으로 추가).

**실제로 울려 봄**: 동시 질문 6개 → 대기열 5 → `LLMQueueBacklog` firing, TTFT p95 약 1분 → `LLMTTFTHigh` pending. 과열 주입 → 1분 뒤 `GPUHighTemperature` critical firing.

**오탐 정리**: Grafana를 `/grafana` 하위 경로로 옮기자 자체 지표 주소가 바뀌어 `TargetDown` → 수집 경로 수정. kind에서 수집 불가한 etcd·scheduler 수집은 껐다.

**면접 한 줄**: "알람은 사람이 행동해야 하는 것만, 증상 중심으로, 지속 조건과 심각도와 대응 문서를 붙여 겁니다."

---

## 7.5 GPU 모니터링: nvidia-smi, DCGM, Xid

**nvidia-smi**: 사람이 보는 GPU 상태 도구(사용률, 메모리, 온도, 전력, 프로세스). `nvidia-smi -q -d PERFORMANCE`로 클럭 저하(throttle) 사유를 본다.

**DCGM (Data Center GPU Manager)**: 데이터센터 GPU 상태 수집·진단 도구다. **dcgm-exporter**가 Prometheus 지표로 내보낸다: `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_GPU_TEMP`, `DCGM_FI_DEV_POWER_USAGE`, `DCGM_FI_DEV_FB_USED/FREE`, `DCGM_FI_DEV_XID_ERRORS`. `dcgmi diag -r 2/3`로 하드웨어 진단도 한다.

**Xid 오류**: NVIDIA 드라이버가 보고하는 GPU 오류 번호(커널 로그 `dmesg`에도 남음).
| Xid | 의미 | 대응 방향 |
|---|---|---|
| **79** | GPU가 PCIe 버스에서 떨어짐 | 하드웨어·전원·발열 의심 → 노드 격리, 재부팅, 재발 시 교체 |
| **48** | 이중 비트 ECC 오류 (메모리 손상, 정정 불가) | 하드웨어 → 교체 검토 |
| **31** | GPU 메모리 페이지 폴트 | 주로 애플리케이션(드라이버) 문제 → 워크로드 로그 확인 |

**GPU 사용률의 함정**: `GPU_UTIL`은 "커널이 하나라도 돌고 있던 시간 비율"이라 100%여도 실제 연산 장치를 꽉 채운 건 아닐 수 있다. 세밀하게는 SM 활용도(`DCGM_FI_PROF_SM_ACTIVE`) 같은 프로파일링 지표를 본다.

**이 프로젝트에서는**: 진짜 GPU가 쿠버네티스에 붙지 않아 **DCGM과 같은 지표 이름·라벨을 내는 시뮬레이터**를 만들었다. 사용률은 게이트웨이의 처리 중 LLM 요청 수, 메모리는 Ollama에 올라간 모델 크기를 따른다. 이름이 같아서 실제 서버에서는 exporter만 dcgm-exporter로 바꾸면 대시보드와 알람을 그대로 쓴다.

**실무 포인트**: 하드웨어(팬, PSU, 온도 센서)는 BMC의 Redfish/SNMP로 따로 수집한다.

**면접 한 줄**: "GPU는 dcgm-exporter로 사용률·메모리·온도·Xid를 수집하고, Xid 79와 48은 하드웨어 문제 가능성이 높아 노드를 격리합니다."

---

## 7.6 CPU throttling — 죽지 않는 장애

**정의**: CPU limit에 닿은 컨테이너를 커널(cgroup CFS)이 일정 주기 안에서 강제로 쉬게 하는 것이다.

**동작 원리**: 100ms 주기마다 limit만큼의 CPU 시간을 쓸 수 있다(500m = 50ms). 다 쓰면 다음 주기까지 멈춘다. 프로세스는 살아 있지만 **응답이 느려지고 타임아웃**이 난다.

**이 프로젝트에서는**: Grafana(limit 500m)가 대시보드 목록에서 몇 분째 로딩만 됐다. Pod 2/3 NotReady, 로그 `Handler timeout`, `kubectl top`에서 CPU가 500m에 딱 붙어 있었다. limit을 1500m으로 올리자 새 Pod가 636m을 쓰며 API가 0.02초에 응답했다.

**면접 한 줄**: "메모리 limit 초과는 OOMKilled로 죽어서 눈에 띄지만, CPU limit 초과는 throttling으로 조용히 느려지기만 해서 kubectl top과 throttling 지표로 찾습니다."
