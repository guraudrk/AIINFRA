# 01. 쿠버네티스 클러스터 — 노드 역할 분리와 GPU 스케줄링

## 한 줄 요약
kind로 4노드(control-plane / app / gpu / data) 클러스터를 만들고, 라벨·taint·확장 리소스(nvidia.com/gpu)로 "GPU가 필요한 Pod만 GPU 노드에, DB는 데이터 노드에" 배치되도록 만든 뒤 Pod 3개로 증명했다.

## 핵심 개념
- **쿠버네티스**는 "이 앱을 이 조건으로 N개 띄워 둬"라고 원하는 상태를 선언하면 계속 그 상태를 유지해 주는 시스템이다. 컨트롤 플레인(API 서버·etcd·스케줄러·컨트롤러 매니저)이 결정하고, 워커 노드의 kubelet이 컨테이너를 실제로 띄운다.
- **라벨 + nodeSelector/affinity**는 "이 Pod는 저 노드로 가고 싶다"(끌어당김)이고, **taint + toleration**은 "이 노드는 허락받은 Pod만 받는다"(밀어냄)이다. GPU 노드는 둘 다 써야 한다. taint만 걸면 GPU Pod가 다른 노드로 갈 수도 있고, 라벨만 쓰면 일반 Pod가 GPU 노드를 차지할 수 있다.
- **확장 리소스(extended resource)**: CPU·메모리 말고 노드가 가진 특수 자원을 `nvidia.com/gpu: 2`처럼 숫자로 광고하는 것이다. 실제로는 **device plugin**이 GPU를 찾아 kubelet에 등록하고, 스케줄러는 남은 개수를 보고 배치한다. GPU는 쪼갤 수 없는 정수 단위이고 limits로 요청한다.
- 비유: 클러스터는 **병원**이다. 스케줄러는 **접수처**, 노드는 **진료실**, 라벨은 진료실 **간판(내과·영상의학과)**이다. taint는 **"MRI실 — 예약 환자만"** 표지판이고, toleration은 환자가 들고 오는 **예약증**, `nvidia.com/gpu: 2`는 **MRI 장비 2대**다. 예약증이 있어도 장비가 다 쓰이고 있으면 대기실(Pending)에서 기다린다.

## 이 프로젝트에서 내가 한 것
- `infra/kind-config.yaml`로 4노드를 선언했다. control-plane에는 `ingress-ready=true`와 80/443 포트 매핑, worker에는 `node-role=app|gpu|data` 라벨을 달았다. gpu 노드에 `nvidia.com/gpu=present:NoSchedule`, data 노드에 `dedicated=data:NoSchedule` taint를 kubeadm JoinConfiguration 패치로 걸었다.
- 기본 CNI(kindnet)는 NetworkPolicy를 실제로 적용하지 않아서 **Calico v3.33.0**으로 교체했다(`disableDefaultCNI: true`, podSubnet 192.168.0.0/16). calico-node DaemonSet이 4개 노드에 모두 뜬 뒤에야 노드가 Ready가 되는 것을 확인했다. CNI가 없으면 노드는 NotReady다.
- GPU 모드는 **SIMULATED**로 했다. WSL2는 GPU를 `/dev/nvidia*`가 아니라 `/dev/dxg`로 노출해서 kind 노드 안 device plugin이 불안정할 위험이 컸고, 면접까지 일정도 고려했다. `scripts/fake-gpu.sh`가 `kubectl proxy`를 띄우고 노드 status 하위 리소스에 JSON Patch(`/status/capacity/nvidia.com~1gpu`)로 GPU 2개를 등록한다.
- 검증 결과 (`infra/tests/placement-test.yaml`):
  | Pod | 조건 | 결과 |
  |---|---|---|
  | gpu-ok | GPU 1 + toleration + nodeSelector gpu | ✅ ax-lab-worker2(gpu)에서 Running, 노드 할당 `nvidia.com/gpu 1/2` |
  | gpu-no-tol | GPU 1, toleration 없음 | ⏸ Pending: `0/4 nodes are available: 1 Insufficient nvidia.com/gpu, 3 node(s) had untolerated taint(s)` |
  | data-ok | nodeSelector data + toleration | ✅ ax-lab-worker3(data)에서 Running |
  - Pending 메시지 해석: app 노드는 taint가 없지만 GPU가 0개라 "Insufficient"이고, 나머지 3개(control-plane, gpu, data)는 taint를 허용하지 않아서 탈락했다. 4개 노드가 각각 왜 탈락했는지 스케줄러가 다 알려 준다.
- 4노드 클러스터의 메모리 사용량은 약 3.3GB(`docker stats`)였다.
- **겪은 문제 3가지**:
  1. `.wslconfig`를 바꾸고 `wsl --shutdown`을 했더니 Docker Desktop 엔진(docker-desktop 배포판)까지 꺼졌다. `kind create`가 "docker could not be found"로 실패했다. `wsl -l -v`에서 docker-desktop이 Stopped인 것을 보고 원인을 찾았고, Docker Desktop을 재시작해서 해결했다.
  2. fake-gpu 직후 `allocatable`이 빈 값이었다. capacity와 allocatable을 따로 조회해 보니 **capacity는 즉시 바뀌고 allocatable은 kubelet이 다음 상태 보고 때 계산**한다는 걸 알게 됐다. 그래서 스크립트에 대기 루프를 넣었다.
  3. Windows 쪽에서 스크립트를 수정하자 실행 권한이 빠져 `Permission denied`가 났다. `ls -l`로 x 비트를 확인하고 `chmod +x`로 복구했다.

## 실제 기업 환경에서는
- **운영 클러스터는 kind가 아니다.** 온프레미스는 OpenShift(Red Hat), RKE2(SUSE), kubeadm 기반 구성을 쓰고, 컨트롤 플레인을 **3대 이상(HA)**으로 둔다. etcd가 과반수(quorum)를 유지해야 해서 홀수 대수로 구성한다. API 서버 앞에는 로드밸런서(VIP)를 둔다.
- **실제 GPU 노드는 GPU Operator**로 관리한다. 드라이버(컨테이너형), Container Toolkit, **device plugin**, GPU Feature Discovery(GPU 모델·메모리를 라벨로 자동 부착), **DCGM exporter**, MIG 매니저를 DaemonSet으로 깔아 준다. 노드를 추가하면 자동으로 GPU 노드가 된다.
- **fake-gpu vs device plugin**:
  | | fake-gpu.sh (이 프로젝트) | NVIDIA device plugin |
  |---|---|---|
  | 개수 등록 | API로 status를 직접 PATCH | GPU를 탐지해 kubelet에 gRPC로 등록 |
  | Pod 안 GPU 장치 | 없음 | `/dev/nvidia0` 등 할당된 GPU만 주입 (`NVIDIA_VISIBLE_DEVICES`) |
  | 장애 GPU | 모름 | 헬스체크로 비정상 GPU를 할당 대상에서 제외 |
  | 같은 것 | 스케줄러가 보는 리소스 이름·개수, Pending 동작, taint/toleration 규칙 | |
- 노드 역할 분리 이유: GPU 서버는 대당 수천만~억 원대라 GPU를 안 쓰는 Pod가 자리를 차지하면 비용 낭비다. DB와 스토리지는 디스크 I/O를 많이 써서 다른 워크로드와 섞이면 지연이 생긴다. 실무에서는 **관리망, 서비스망, 스토리지망, GPU 연산망**까지 네트워크도 분리한다(M5).

## 에티버스그룹 사업과의 연결
이테크시스템이 Dell AI Factory 기반으로 구축하는 플랫폼도 결국 "GPU 노드를 어떤 워크로드가 언제 쓰느냐"를 쿠버네티스(또는 OpenShift) 스케줄링으로 통제하는 구조다. 고객이 "GPU가 노는데 Pod가 Pending이에요"라고 문의하면, 오늘처럼 `describe pod`의 Events와 노드 Allocated resources부터 보는 게 첫 진단 순서가 된다.

## 자주 쓰는 명령어
```bash
kind create cluster --config infra/kind-config.yaml   # 클러스터 생성
kubectl get nodes -L node-role                        # 노드 + 라벨 열
kubectl describe node <노드>                           # Taints, Capacity/Allocatable, Allocated resources
kubectl get node <노드> -o jsonpath='{.status.allocatable}'
kubectl taint nodes <노드> key=value:NoSchedule        # taint 추가 (끝에 - 붙이면 제거)
kubectl label nodes <노드> node-role=gpu               # 라벨 추가
kubectl get pods -A -o wide                           # Pod가 어느 노드에 있는지
kubectl describe pod <pod>                            # Events: FailedScheduling 이유
kubectl get events -A --sort-by=.lastTimestamp        # 최근 이벤트
```

## 예상 면접 질문 5개 + 모범 답변

**Q1. 쿠버네티스 구성요소를 설명해 주세요.**
> 크게 컨트롤 플레인과 워커 노드로 나뉩니다. 컨트롤 플레인에는 모든 요청을 받는 API 서버, 클러스터 상태를 저장하는 etcd, Pod를 어느 노드에 둘지 정하는 스케줄러, 원하는 상태를 맞춰 주는 컨트롤러 매니저가 있습니다. 워커 노드에는 컨테이너를 실제로 띄우는 kubelet, 서비스 트래픽 규칙을 만드는 kube-proxy, 그리고 containerd 같은 런타임이 있습니다. 제 프로젝트에서는 kind로 컨트롤 플레인 1대, 워커 3대를 만들었는데요, 운영 환경이라면 etcd quorum 때문에 컨트롤 플레인을 3대 이상으로 두는 게 기본이라고 알고 있습니다.

**Q2. taint/toleration과 nodeSelector(affinity)의 차이는 뭔가요? GPU 노드에는 뭘 써야 하나요?**
> nodeSelector는 Pod가 특정 노드로 가겠다고 끌어당기는 거고, taint는 노드가 허락 안 한 Pod를 밀어내는 겁니다. GPU 노드는 둘 다 필요하다고 생각합니다. taint만 걸면 GPU Pod가 다른 데로 갈 수도 있고, nodeSelector만 쓰면 일반 Pod가 비싼 GPU 노드를 차지할 수 있어서요. 실제로 GPU 노드에 `nvidia.com/gpu=present:NoSchedule` taint를 걸고 toleration 없는 GPU Pod를 띄워 봤는데, Pending이 되면서 "3개 노드는 taint 때문에, 1개는 GPU 부족으로 안 된다"는 메시지가 그대로 나왔습니다.

**Q3. Pod가 GPU를 요청했는데 Pending입니다. 어떻게 확인하시겠어요?**
> 먼저 `kubectl describe pod`로 Events의 FailedScheduling 메시지를 봅니다. 노드별 탈락 이유가 나오니까요. "Insufficient nvidia.com/gpu"면 `describe node`에서 GPU가 Capacity에 잡혀 있는지, 다른 Pod가 이미 다 쓰고 있는지(Allocated resources) 봅니다. Capacity에 아예 없으면 device plugin Pod가 죽었거나 드라이버 문제일 수 있어서 device plugin 로그랑 노드에서 `nvidia-smi`를 확인하겠습니다. "untolerated taint"면 Pod 스펙에 toleration이 빠진 거고요. 제가 이 순서를 실제로 해 봤는데, 테스트 Pod로 Pending을 일부러 만들어서 확인했습니다.

**Q4. device plugin과 GPU Operator는 각각 뭘 하나요?**
> device plugin은 노드의 GPU를 찾아서 kubelet에 "GPU 몇 개 있다"고 등록하고, Pod가 GPU를 받으면 그 GPU 장치만 컨테이너에 넣어 주는 역할입니다. GPU Operator는 그걸 포함해서 드라이버, Container Toolkit, GPU 정보를 라벨로 붙이는 Feature Discovery, DCGM 모니터링까지 한꺼번에 설치·관리해 주는 도구입니다. 제 PC는 WSL이라 device plugin이 GPU를 제대로 못 잡을 위험이 있어서, 노드 status에 GPU 2개를 API로 직접 등록하는 방식으로 대신했습니다. 스케줄링 동작은 똑같이 검증되지만 Pod 안에 실제 GPU가 들어가진 않는다는 차이는 분명히 말씀드리고 싶습니다.

**Q5. kind로 만든 클러스터와 실제 운영 클러스터는 뭐가 다른가요?**
> kind는 노드를 Docker 컨테이너로 띄워서 PC 한 대로 멀티 노드를 흉내 내는 테스트용 도구입니다. 운영 환경은 OpenShift나 RKE2처럼 지원되는 배포판을 쓰고, 컨트롤 플레인을 3대 이상 HA로 구성하고, 앞단에 로드밸런서를 둡니다. 스토리지도 kind는 노드 로컬 디스크를 쓰지만 운영에서는 외부 스토리지를 CSI로 붙이고, GPU도 실제 장비에 GPU Operator를 씁니다. 그래서 저는 kind로 개념과 스케줄링 동작을 검증했고, 운영 환경 구성은 문서로 정리하면서 차이를 따로 기록해 두었습니다.

## 꼬리 질문 3개 + 답변 방향
1. **"GPU를 requests 말고 limits에 쓰는 이유는?"** → 확장 리소스는 오버커밋이 안 된다. limits만 써도 requests가 같은 값으로 자동 설정되고, requests와 limits를 다르게 쓸 수 없다. GPU는 정수 단위로 통째로 할당하고, 쪼개 쓰려면 MIG나 time-slicing이 필요하다(M2 노트).
2. **"StatefulSet은 Deployment와 뭐가 달라요?"** → Pod 이름과 순서가 고정되고(postgres-0), Pod마다 전용 PVC가 붙는다. DB처럼 "누가 누구인지"가 중요한 앱에 쓴다. M3에서 PostgreSQL을 StatefulSet으로 data 노드에 올린다.
3. **"Calico를 왜 썼어요?"** → kind 기본 CNI(kindnet)는 NetworkPolicy를 만들어도 실제로 차단하지 않는다. M5에서 기본 거부 정책을 걸고 curl로 차단을 증명하려고 Calico를 골랐다. 대가로 노드마다 calico-node가 떠서 자원을 조금 더 쓴다.
