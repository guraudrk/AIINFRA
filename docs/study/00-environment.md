# 00. 환경 — WSL2, 컨테이너, GPU 드라이버 스택

## 한 줄 요약
Windows PC에 WSL2(Ubuntu)와 Docker Desktop을 연동하고, 드라이버 → CUDA → Container Toolkit 순으로 GPU가 컨테이너 안까지 보이는 것을 확인해서 이 프로젝트를 REAL GPU 모드로 시작했다.

## 핵심 개념
- **WSL2**는 Windows 안에서 진짜 리눅스 커널을 경량 VM(Hyper-V)으로 돌리는 기능이다. 쿠버네티스·컨테이너 도구는 리눅스 기준이라 실제 서버와 같은 환경에서 연습할 수 있다.
- **컨테이너 vs VM**: VM은 하드웨어를 가상화해 OS를 통째로 하나 더 띄우고, 컨테이너는 호스트 커널을 공유하면서 namespace(격리)와 cgroup(자원 제한)으로 프로세스를 나눈다. 그래서 컨테이너가 가볍고 빨리 뜬다.
- **GPU 스택은 세 층**이다. ① 드라이버(커널 모듈, GPU와 대화) ② CUDA(GPU 연산용 라이브러리·런타임, 대부분 컨테이너 이미지 안에 들어감) ③ NVIDIA Container Toolkit(컨테이너를 만들 때 호스트의 드라이버와 장치 파일을 컨테이너 안에 넣어 줌).
- 비유: 드라이버는 **건물의 전기 배선**, CUDA는 **전기를 쓰는 가전제품**, Container Toolkit은 **세입자 방(컨테이너)에 콘센트를 달아 주는 전기 기사**다. 가전(CUDA)은 세입자가 들고 오지만 배선(드라이버)은 건물에 하나뿐이다.

## 이 프로젝트에서 내가 한 것
- 내 PC(Ryzen 5 5600 6코어, RAM 16GB, RTX 4060 8GB)에서 WSL2 Ubuntu 26.04와 Docker Desktop의 WSL Integration을 켰다. 켜기 전에는 Ubuntu 안 `docker`가 Windows 쪽 docker.exe를 가리키고 있었는데, 켠 뒤에는 `/usr/bin/docker` → `/var/run/docker.sock`으로 바뀐 것을 확인했다.
- `.wslconfig`로 WSL 메모리를 기본 7GB에서 12GB로 올렸다. kind 4노드, LLM, Postgres, Prometheus를 동시에 띄우려면 7GB로는 부족하다고 판단했다.
- kubectl v1.37.1(sha256 검증), kind v0.33.0, helm v4.3.0, make, psql을 설치했다.
- `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`로 컨테이너 안에서 GPU가 보이는 것을 확인했다. 그래서 GPU 모드를 REAL로 정했다.
- 점검하다가 VRAM 8GB 중 5.2GB를 이미 Windows 화면과 앱이 쓰고 있다는 걸 발견했다. 그래서 sLLM을 7B가 아니라 **3B(Q4, 약 1.9GB)**로 정했다. "가중치 ≈ 파라미터 × 바이트"로 계산한 결과다.

## 실제 기업 환경에서는
- 데이터센터 GPU 서버(Dell PowerEdge XE9680, HPE 등)는 WSL이 아니라 **베어메탈 RHEL/Ubuntu**에 직접 드라이버를 설치한다. 컨테이너 플랫폼으로는 쿠버네티스나 OpenShift를 쓴다.
- **실제 GPU 서버 구축 순서**:
  1. 랙 실장·전원(이중화 PSU, 랙당 전력·발열 용량 확인)·케이블링
  2. **BMC(iDRAC / iLO) 관리망** 연결 → 원격 전원, 콘솔, 펌웨어(BIOS·NIC·GPU) 업데이트
  3. OS 설치 (RHEL / Ubuntu, 폐쇄망이면 내부 저장소 미러)
  4. NVIDIA 드라이버 → CUDA → Container Toolkit (+ 멀티 GPU 서버는 Fabric Manager, NVLink 확인)
  5. 쿠버네티스 / OpenShift 구성 + **GPU Operator**(드라이버, Toolkit, device plugin, DCGM exporter를 DaemonSet으로 자동 배포)
  6. 모니터링 (DCGM exporter → Prometheus/Grafana, BMC 하드웨어 알람)
  7. **인수 테스트**: `nvidia-smi`, DCGM 진단(`dcgmi diag -r 3`), NCCL 대역폭 테스트, burn-in 부하 테스트, 고객과 결과 서명
- 폐쇄망 고객은 드라이버 패키지, 컨테이너 이미지, 모델 파일을 미리 반입해야 해서 **버전 호환표(드라이버 ↔ CUDA ↔ 프레임워크)**를 구축 전에 확정한다.

## 에티버스그룹 사업과의 연결
이테크시스템은 Dell AI Factory 기반으로 OS·GPU 드라이버·스위치·모니터링까지 통합 구축한다. 오늘 확인한 드라이버 → CUDA → Toolkit → 컨테이너 순서가 그 구축 작업의 가장 아래층이다. 고객 현장에서 처음 하는 점검도 결국 "nvidia-smi가 호스트와 컨테이너 양쪽에서 보이는가"라서, 이 점검 순서를 그대로 런북으로 쓸 수 있다.

## 자주 쓰는 명령어
```bash
wsl -l -v                         # (Windows) 배포판·WSL 버전
nvidia-smi                        # GPU, 드라이버, VRAM, 사용률
nvidia-smi -L                     # GPU 목록·UUID
nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu --format=csv
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi  # 컨테이너 GPU 확인
docker info | grep -i runtime     # nvidia 런타임 등록 여부
free -h; nproc; df -h             # 메모리, 코어, 디스크
uname -r; cat /etc/os-release     # 커널, OS 버전
lspci | grep -i nvidia            # (베어메탈) PCIe에 GPU가 잡히는지
```

## 예상 면접 질문 5개 + 모범 답변

**Q1. 컨테이너와 VM의 차이를 설명해 주세요.**
> VM은 하이퍼바이저 위에 게스트 OS를 통째로 하나 더 올리는 방식이고, 컨테이너는 호스트 커널을 같이 쓰면서 리눅스 namespace로 프로세스, 네트워크, 파일시스템을 격리하고 cgroup으로 CPU나 메모리를 제한하는 방식입니다. 그래서 컨테이너가 훨씬 가볍고 빨리 뜨지만, 커널을 공유하니까 격리 수준은 VM보다 약합니다. 이번 프로젝트에서 쓰는 kind도 쿠버네티스 노드를 VM이 아니라 Docker 컨테이너로 띄우는 도구라서, 16GB PC 한 대에서 4노드 클러스터를 구성할 수 있습니다.

**Q2. 컨테이너에서 GPU를 쓰려면 무엇이 필요한가요?**
> 세 층으로 이해하고 있습니다. 호스트에 NVIDIA 드라이버, 컨테이너 이미지 안에 CUDA 런타임, 그리고 그 둘을 이어 주는 NVIDIA Container Toolkit입니다. Toolkit이 컨테이너를 만들 때 호스트의 드라이버 라이브러리와 /dev/nvidia 장치를 컨테이너에 넣어 주는 역할을 합니다. 그래서 드라이버는 호스트에 한 번만 깔고, CUDA 버전은 이미지마다 달라도 되는데, 단 드라이버가 그 CUDA 버전보다 같거나 새 버전이어야 합니다. 저는 실제로 `docker run --gpus all ... nvidia-smi`로 컨테이너 안에서 GPU가 보이는지 확인하고 시작했습니다.

**Q3. 고객사에 GPU 서버가 들어왔다면, 서비스 올리기 전까지 어떤 순서로 작업하나요?**
> 실장과 전원·케이블링 다음에 먼저 iDRAC이나 iLO 같은 BMC를 관리망에 연결해서 원격으로 전원이나 콘솔, 펌웨어 업데이트를 할 수 있게 해 둡니다. 그다음 OS를 깔고, 드라이버·CUDA·Container Toolkit 순으로 올린 뒤에, 쿠버네티스나 OpenShift를 구성하고 GPU Operator로 device plugin이랑 DCGM exporter를 배포합니다. 마지막으로 모니터링을 붙이고 DCGM 진단이나 부하 테스트로 인수 테스트를 합니다. 다만 실제 랙 작업이나 BMC 설정은 제가 아직 현장에서 해 본 적은 없어서, 순서와 목적을 이해한 수준이라고 말씀드리는 게 정확할 것 같습니다.

**Q4. WSL2로 연습한 환경이 실제 서버와 어떻게 다른가요?**
> 커널과 도구는 진짜 리눅스라서 kubectl, helm, 셸 스크립트 같은 건 서버랑 그대로 같습니다. 차이는 하드웨어 계층인데요, WSL에서는 GPU 드라이버가 Windows에 설치되어 있고 WSL은 그걸 공유받는 구조라서, 베어메탈처럼 커널 모듈을 직접 설치하거나 BMC, NVLink, ECC 같은 걸 다룰 수는 없습니다. 실제로 이번에 보니 Windows 화면이 VRAM을 5GB 넘게 쓰고 있어서, 서버였다면 신경 쓰지 않아도 될 제약 때문에 모델을 3B로 줄였습니다. 그래서 문서에 실제 환경과의 차이를 따로 적어 두었습니다.

**Q5. GPU 메모리를 보고 어떻게 모델 크기를 정했나요?**
> 가중치 메모리는 대략 파라미터 수 곱하기 파라미터당 바이트로 계산했습니다. 7B를 FP16으로 올리면 14GB라 8GB 카드에는 안 들어가고, 4비트 양자화면 3.5GB 정도인데 저는 여유 VRAM이 3GB밖에 없었습니다. 그래서 3B 모델의 4비트 버전, 약 1.9GB를 골랐고, 남는 공간이 KV 캐시랑 임베딩 모델 몫입니다. 실제 속도는 다음 단계에서 동시 요청별 TTFT와 초당 토큰으로 측정해서 근거를 남길 계획입니다.

## 꼬리 질문 3개 + 답변 방향
1. **"드라이버 버전과 CUDA 버전이 안 맞으면 어떻게 되나요?"** → CUDA는 드라이버와 하위 호환이므로 드라이버가 더 새 버전이면 괜찮고, 반대면 `CUDA driver version is insufficient` 에러가 난다. `nvidia-smi` 오른쪽 위의 CUDA Version은 드라이버가 지원하는 **최대** 버전이다(내 PC는 13.1, 이미지는 12.4라서 OK).
2. **"GPU Operator를 쓰면 뭐가 좋아요?"** → 노드마다 손으로 드라이버, Toolkit, device plugin, DCGM을 설치하는 대신 DaemonSet으로 일관되게 배포하고 업그레이드한다. 노드를 추가해도 자동 적용된다. M1 노트에서 자세히 다룬다.
3. **"폐쇄망이면 드라이버는 어떻게 설치해요?"** → 인터넷이 되는 곳에서 OS 버전에 맞는 패키지와 의존성, 컨테이너 이미지(드라이버 컨테이너 포함), 모델 파일을 받아 해시와 함께 반입한다. 내부 저장소(yum/apt 미러, 내부 레지스트리)를 구성해 설치한다. M5 폐쇄망 리허설과 연결된다.
