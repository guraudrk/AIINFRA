# 2장. 쿠버네티스

> 관련: M1 클러스터 · 노트 [01-cluster](../study/01-cluster.md)

## 2.1 쿠버네티스란: 선언형과 조정 루프

**정의**: 쿠버네티스는 여러 서버(노드)에 컨테이너를 배치하고, 죽으면 다시 살리고, 개수를 늘리고 줄이는 **컨테이너 오케스트레이션 플랫폼**이다.

**왜 필요한가**: 서버가 수십 대, 컨테이너가 수백 개면 사람이 "어느 서버에 무엇을 띄울지", "죽으면 다시 띄우기"를 할 수 없다. 쿠버네티스가 이걸 자동화한다.

**동작 원리 — 선언형(declarative)과 조정 루프(reconciliation loop)**
1. 사용자는 "어떻게"가 아니라 **"원하는 상태"**를 YAML로 선언한다. 예: "이 이미지로 Pod 3개를 유지해 줘".
2. 선언은 **API 서버**를 거쳐 **etcd**에 저장된다.
3. **컨트롤러**들이 계속 "원하는 상태"와 "실제 상태"를 비교하고, 차이가 있으면 맞춘다(Pod가 2개면 하나 더 만든다).
4. 이 비교-조치가 끝없이 반복되는 것이 **조정 루프**다. 그래서 장애가 나도 스스로 원래 상태로 돌아가려 한다.

**이 프로젝트에서는**: M8 시나리오 4에서 postgres-0 Pod를 강제로 지웠는데, StatefulSet 컨트롤러가 "1개여야 하는데 0개"를 감지하고 약 9초 만에 같은 이름·같은 디스크로 다시 만들었다.

**흔한 오해**: "kubectl로 명령하면 쿠버네티스가 그 명령을 실행한다" → 정확히는 **원하는 상태를 바꿀 뿐**이고, 실제 실행은 컨트롤러와 kubelet이 비동기로 한다. 그래서 `apply`가 성공해도 Pod가 바로 뜨는 건 아니다(Helm 배포 성공 ≠ 서비스 정상, 9장).

**면접 한 줄**: "쿠버네티스는 원하는 상태를 선언하면 컨트롤러가 실제 상태를 계속 비교해 맞추는 조정 루프로 동작합니다."

---

## 2.2 구성요소

**컨트롤 플레인 (두뇌)**
| 구성요소 | 역할 | 비유 |
|---|---|---|
| **kube-apiserver** | 모든 요청의 단일 창구. 인증·인가·검증 후 etcd에 저장 | 병원 대표 창구 |
| **etcd** | 클러스터 상태를 저장하는 분산 키-값 저장소. **과반수(quorum)**가 동의해야 기록 확정 → 3·5대 홀수로 구성 | 진료 기록 보관실 |
| **kube-scheduler** | 새 Pod를 어느 노드에 둘지 결정 (2.4절) | 접수처 |
| **kube-controller-manager** | Deployment·StatefulSet·Job 등 컨트롤러 묶음. 조정 루프 실행 | 수간호사 |

**워커 노드 (손발)**
| 구성요소 | 역할 |
|---|---|
| **kubelet** | 노드에 배정된 Pod를 컨테이너 런타임에 실행시키고, probe 검사와 상태 보고를 한다 |
| **컨테이너 런타임** (containerd, CRI-O) | 실제 컨테이너 생성·실행 |
| **kube-proxy** | Service IP로 온 트래픽을 실제 Pod IP로 보내는 규칙(iptables/IPVS)을 만든다 |
| **CNI 플러그인** (Calico 등) | Pod에 IP를 주고 노드 간 Pod 통신을 연결한다 |

**실무 포인트 — 고가용성(HA)**: 운영 클러스터는 컨트롤 플레인을 **3대 이상**으로 둔다. etcd는 3대 중 2대, 5대 중 3대가 살아 있어야 쓰기가 가능하다. API 서버 앞에는 로드밸런서(VIP)를 둔다. kind는 1대라 HA가 아니다.

**면접 한 줄**: "API 서버가 창구, etcd가 저장소, 스케줄러가 배치, 컨트롤러가 조정을 맡고, 노드에서는 kubelet이 실제로 컨테이너를 띄웁니다."

---

## 2.3 워크로드 객체

| 객체 | 언제 쓰나 | 특징 | 이 프로젝트 |
|---|---|---|---|
| **Pod** | 배치 최소 단위 | 컨테이너 1개 이상 + 같은 IP·볼륨 공유. 직접 만들기보다 상위 객체가 만든다 | 모든 앱 |
| **Deployment** | 상태 없는 앱 | 같은 Pod N개 유지, 롤링 업데이트·롤백. Pod 이름은 무작위 | ax-gateway, web-ui, LLM 서빙 |
| **StatefulSet** | 상태 있는 앱(DB) | Pod 이름 고정(`postgres-0`), Pod마다 전용 PVC, 순서 있는 생성·종료 | PostgreSQL, MinIO |
| **DaemonSet** | 노드마다 하나 | 노드가 추가되면 자동 배치 | Calico, node-exporter, GPU 시뮬레이터 |
| **Job / CronJob** | 한 번 / 주기적 실행 | 성공할 때까지 재시도(backoffLimit), 기록 보관 개수 | 모델 적재, 수집, 백업 |
| **Service** | 고정 주소 | Pod가 바뀌어도 같은 이름·IP. Ready인 Pod에만 트래픽 | 모든 서버 앱 |

**업데이트 전략**
- **RollingUpdate**(기본): 새 Pod를 띄우고 준비되면 옛 Pod를 줄인다 → 무중단.
- **Recreate**: 옛 Pod를 **먼저 모두 지우고** 새 Pod를 만든다 → 잠깐 중단되지만, GPU나 RWO 디스크처럼 **동시에 두 벌을 띄울 수 없는 자원**에 쓴다.

**이 프로젝트에서는**: LLM 서빙을 Recreate로 했다. M8 시나리오 3(GPU 3개 요청)에서 옛 Pod가 먼저 지워지고 새 Pod가 Pending이 되어 **LLM이 0개**가 됐다. Recreate의 대가를 직접 본 사례다.

**흔한 오해**: "StatefulSet이면 데이터가 안전하다" → 이름과 디스크 연결만 보장한다. **복제·백업은 별도**다(8장).

**면접 한 줄**: "상태 없는 앱은 Deployment, DB처럼 이름과 디스크가 고정돼야 하는 앱은 StatefulSet, 노드마다 하나씩은 DaemonSet을 씁니다."

---

## 2.4 스케줄링: 라벨, 어피니티, taint와 toleration

**정의**: 스케줄러가 새 Pod를 어느 노드에 둘지 정하는 과정이다.

**동작 원리 — 두 단계**
1. **필터링(Filtering)**: 조건에 안 맞는 노드를 뺀다.
   - 자원: 노드의 남은 allocatable ≥ Pod의 requests인가 (CPU, 메모리, `nvidia.com/gpu`)
   - nodeSelector / node affinity: 라벨 조건에 맞는가
   - taint / toleration: 노드의 taint를 Pod가 허용하는가
   - 볼륨: PVC가 붙을 수 있는 노드인가
2. **점수 매기기(Scoring)**: 남은 노드 중 자원 균형 등으로 점수를 매겨 가장 좋은 노드를 고른다.
3. 남는 노드가 없으면 **Pending**이 되고, 이유를 Events의 `FailedScheduling`에 노드별로 남긴다.

**라벨 + nodeSelector vs taint + toleration**
| | 방향 | 의미 |
|---|---|---|
| nodeSelector / affinity | Pod → 노드 (끌어당김) | "나는 GPU 노드로 가고 싶다" |
| taint / toleration | 노드 → Pod (밀어냄) | "허락받은 Pod만 이 노드에 와라" |

GPU 노드에는 **둘 다** 쓴다. taint만 걸면 GPU Pod가 다른 노드로 갈 수 있고, 라벨만 쓰면 일반 Pod가 비싼 GPU 노드를 차지할 수 있다.

**taint 효과(effect)**: `NoSchedule`(새 Pod 거부), `PreferNoSchedule`(가급적 거부), `NoExecute`(이미 있는 Pod도 쫓아냄).

**이 프로젝트에서는**: GPU 노드에 `nvidia.com/gpu=present:NoSchedule`, 데이터 노드에 `dedicated=data:NoSchedule`을 걸었다. toleration 없는 GPU Pod는 `0/4 nodes are available: 1 Insufficient nvidia.com/gpu, 3 node(s) had untolerated taint(s)`로 Pending이었다. 노드 4대가 각각 왜 탈락했는지 메시지에 다 나온다.

**흔한 오해**: "toleration이 있으면 그 노드로 간다" → 아니다. toleration은 **허용**일 뿐 끌어당기지 않는다. 그래서 nodeSelector와 함께 쓴다.

**면접 한 줄**: "라벨과 nodeSelector는 Pod가 노드를 고르는 것이고, taint와 toleration은 노드가 Pod를 거르는 것이라 GPU 노드에는 둘 다 걸어야 합니다."

---

## 2.5 자원: requests, limits, QoS

**정의**
- **requests**: "최소 이만큼은 보장해 줘". **스케줄링 기준**이다.
- **limits**: "최대 이만큼까지만 써". **실행 중 강제 상한**이다(cgroup).

**동작 원리**
- 스케줄러는 노드의 allocatable에서 이미 배치된 Pod들의 **requests 합**을 빼고 남은 만큼만 새 Pod를 받는다(실제 사용량이 아님).
- 실행 중 메모리가 limits를 넘으면 **OOMKilled(Exit 137)**, CPU가 limits에 닿으면 **throttling**.
- **QoS 클래스**: requests=limits면 Guaranteed, requests<limits면 Burstable, 둘 다 없으면 BestEffort. 노드 메모리가 부족하면 BestEffort → Burstable 순으로 먼저 쫓겨난다.

**이 프로젝트에서는**: LLM 서빙 메모리를 "가중치 1.9GB + KV 캐시 0.6GB + 여유 0.5GB ≈ 3GB"로 계산해 requests 3Gi, limits 4Gi로 잡고 근거를 values에 주석으로 남겼다. M8에서 이를 512Mi로 줄이자 OOMKilled가 났다.

**흔한 오해**: "limits를 넉넉히 주면 안전하다" → 노드 전체로 보면 limits 합이 실제 메모리보다 크면(오버커밋) 노드 메모리 부족 시 여러 Pod가 같이 죽을 수 있다. requests는 실측 기반으로 정한다.

**면접 한 줄**: "requests는 스케줄링 기준이고 limits는 실행 중 상한입니다. 메모리 limit 초과는 OOMKilled, CPU limit 초과는 throttling입니다."

---

## 2.6 확장 리소스, device plugin, GPU Operator

**정의**: CPU·메모리 외의 특수 자원을 `nvidia.com/gpu: 2`처럼 숫자로 광고하는 것이 **확장 리소스**다. 이를 실제로 탐지·등록·할당하는 것이 **device plugin**이다.

**동작 원리**
1. NVIDIA device plugin(DaemonSet)이 노드의 GPU를 찾는다.
2. kubelet에 gRPC로 "GPU 2개 있음"을 등록 → 노드 status의 capacity/allocatable에 반영된다.
3. Pod가 `limits: nvidia.com/gpu: 1`을 요청하면 스케줄러가 남은 GPU를 보고 배치한다.
4. kubelet이 device plugin에 할당을 요청하면, 그 GPU 장치만 컨테이너에 넣어 준다.
- GPU는 **정수 단위·오버커밋 불가**다. limits만 쓰면 requests가 같은 값으로 잡힌다.

**GPU Operator**: 드라이버(컨테이너형), Container Toolkit, device plugin, GPU Feature Discovery(GPU 모델을 노드 라벨로), DCGM exporter(모니터링), MIG 매니저를 **한 번에 설치·관리**한다. 노드를 추가하면 자동으로 GPU 노드가 된다.

**GPU 공유**: MIG(A100·H100을 하드웨어로 최대 7조각, 격리 강함), time-slicing(시간 분할, 격리 없음), MPS(동시 실행, 메모리 격리 약함).

**이 프로젝트에서는**: device plugin 대신 `fake-gpu.sh`로 노드 status에 `nvidia.com/gpu: 2`를 JSON Patch로 직접 넣었다(SIMULATED). 스케줄링 동작은 같지만 Pod 안에 GPU 장치는 없다. 재부팅 후에도 등록이 유지되는 것을 확인했다.

**면접 한 줄**: "device plugin이 GPU를 확장 리소스로 등록하면 스케줄러가 개수로 배치하고, GPU Operator는 드라이버부터 모니터링까지 그 전체를 자동화합니다."

---

## 2.7 Probe: startup, readiness, liveness

| Probe | 질문 | 실패하면 |
|---|---|---|
| **startupProbe** | "다 켜졌나?" | 통과 전까지 다른 probe를 미룬다. 기한 초과 시 재시작 |
| **readinessProbe** | "트래픽 받을 준비 됐나?" | **Service 엔드포인트에서 제외**(재시작 안 함) → READY 0/1 |
| **livenessProbe** | "살아 있나?" | **컨테이너 재시작** |

**설계 원칙**
- liveness는 **재시작하면 고쳐지는 문제**만 검사한다. DB 장애로 앱을 재시작해도 안 고쳐지므로, DB 연결은 readiness에 둔다(ax-gateway: readiness `/readyz`=DB 확인, liveness `/healthz`=프로세스만).
- 느리게 뜨는 앱(모델 로딩)은 startupProbe로 보호해 liveness가 일찍 죽이지 않게 한다.

**이 프로젝트에서는**
- LLM 서빙 readiness를 "모델이 PVC에 있는가(`ollama show`)"로 해서, 모델 없는 Pod가 트래픽을 받지 않게 했다.
- 그 결과 M2에서 **Service는 Ready Pod에만 연결 → 모델 적재 Job이 접속 불가 → 모델이 없어 Ready 불가**인 교착이 생겼고, NotReady에도 연결되는 관리용 headless Service(`publishNotReadyAddresses`)로 풀었다.
- M8 시나리오 2(없는 모델 이름)는 readiness 실패로 READY 0/1이 되어, 이상한 오류를 사용자에게 내는 대신 조용히 빠지고 원인이 Events에 남았다.

**면접 한 줄**: "readiness는 트래픽을 받을지, liveness는 재시작할지를 정하는 검사라서, 재시작으로 안 고쳐지는 의존성 장애는 readiness에만 둡니다."

---

## 2.8 Helm과 선언형 배포 관리

**정의**: Helm은 여러 쿠버네티스 매니페스트를 **템플릿 + 값(values)**으로 묶은 패키지(차트)를 설치·업그레이드·롤백하는 도구다.

**동작 원리**: `helm upgrade`는 values를 템플릿에 넣어 매니페스트를 렌더링하고, 릴리스 리비전으로 기록한 뒤 클러스터에 적용한다. hook(post-install 등)으로 마이그레이션 Job 같은 작업을 끼워 넣을 수 있다.

**이 프로젝트에서 겪은 두 가지 함정**
1. **필드 소유권 충돌**: Helm 4는 server-side apply로 필드마다 관리자를 기록한다. `kubectl set env`로 직접 고치자 다음 `helm upgrade`가 `conflict with "kubectl-set"`으로 실패했다 → Helm이 관리하는 리소스는 Helm으로만 바꾼다(`--force-conflicts`로 소유권 회수).
2. **원복이 원복이 아님**: `--set`으로 장애를 넣은 뒤 값 없이 `helm upgrade`하면 직전에 덮어쓴 값이 다시 적용되는 동작 때문에 원복이 안 됐다 → `--reset-values`를 명시하고 원복 후 실제 값을 검증했다.

**흔한 오해**: "helm upgrade가 성공했으면 배포가 끝났다" → 쿠버네티스에 설정을 넣었을 뿐이다. `--wait`와 `--rollback-on-failure`(이전 이름 `--atomic`)로 준비까지 확인해야 한다.

**면접 한 줄**: "Helm은 템플릿과 값으로 배포를 버전 관리하는 도구이고, 운영에서는 Helm으로 관리하는 리소스를 kubectl로 직접 고치지 않는 게 원칙입니다."
