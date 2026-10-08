# 6장. 네트워크, TLS, 네트워크 정책, 폐쇄망

> 관련: M5 · 노트 [05-network-security](../study/05-network-security.md) · [폐쇄망 절차서](../airgap-install.md)

## 6.1 네트워크 계층 모델과 L4·L7

**정의**: OSI 7계층은 통신을 단계별로 나눈 모델이다. 실무에서는 TCP/IP 4계층으로 단순화해 말하는 경우가 많다.

| 계층 | 하는 일 | 주소·단위 | 장비·예 |
|---|---|---|---|
| L2 데이터링크 | 같은 네트워크 안 전달 | MAC, 프레임 | 스위치, VLAN |
| L3 네트워크 | 네트워크 사이 경로 찾기 | IP, 패킷 | 라우터 |
| L4 전송 | 프로세스 간 연결 | **포트**, TCP/UDP | L4 로드밸런서, kube-proxy |
| L7 응용 | 애플리케이션 의미 | HTTP 경로·헤더 | Ingress, API 게이트웨이 |

**TCP vs UDP**: TCP는 연결을 맺고(3-way handshake) 순서·도착을 보장한다(웹, DB). UDP는 확인 없이 보낸다(DNS 조회, 영상).

**L4 vs L7 부하 분산**: L4는 IP·포트만 보고 넘긴다(빠름). L7은 HTTP 내용(`/api` 경로, 호스트 이름)까지 보고 판단한다(경로 라우팅, TLS 종료 가능).

**면접 한 줄**: "L4는 IP와 포트만 보고 넘기고, L7은 HTTP 경로까지 보고 판단해서 Ingress는 L7에서 경로별로 서비스를 나눕니다."

---

## 6.2 쿠버네티스 네트워크: CNI, Service, kube-proxy, DNS

**네 가지 통신**
1. **컨테이너 ↔ 컨테이너 (같은 Pod)**: localhost로 통신(네트워크 namespace 공유).
2. **Pod ↔ Pod**: 모든 Pod는 고유 IP를 갖고 NAT 없이 서로 통신한다는 것이 쿠버네티스 네트워크 모델이다. 이걸 **CNI 플러그인**(Calico, Cilium 등)이 구현한다. Calico는 노드 간 라우팅(BGP 또는 터널)으로 Pod IP 대역(192.168.0.0/16)을 연결한다.
3. **Pod → Service**: Service는 고정 가상 IP(ClusterIP, 10.96.x.x)를 갖는다. **kube-proxy**가 각 노드에 iptables/IPVS 규칙을 만들어, 그 IP로 온 패킷을 **Ready인 Pod**들 중 하나로 바꿔 보낸다(EndpointSlice 목록 기준).
4. **외부 → 클러스터**: Ingress(L7) 또는 LoadBalancer/NodePort(L4).

**DNS (CoreDNS)**: `postgres`라는 이름을 Service IP로 바꿔 준다. Pod의 `/etc/resolv.conf`에 `search ai-platform.svc.cluster.local ...`이 있어서 짧은 이름이 동작한다. 전체 이름(FQDN)은 `postgres.ai-platform.svc.cluster.local`. (busybox nslookup은 검색 도메인 중 마지막 실패를 종료 코드로 남겨서 FQDN으로 물어야 했다.)

**headless Service**: ClusterIP 없이(`clusterIP: None`) DNS가 Pod IP를 바로 돌려준다. `publishNotReadyAddresses: true`면 NotReady Pod도 포함된다 → M2 모델 적재 교착 해결에 썼다.

**면접 한 줄**: "Pod 간 통신은 CNI가, Service 가상 IP에서 실제 Pod로 보내는 건 kube-proxy가, 이름을 IP로 바꾸는 건 CoreDNS가 합니다."

---

## 6.3 Ingress, Ingress 컨트롤러, Gateway API

**정의**: **Ingress**는 "이 호스트·경로로 오면 이 서비스로 보내라"는 L7 라우팅 규칙이고, 그 규칙을 실제로 실행하는 프로그램이 **Ingress 컨트롤러**(Traefik, HAProxy, 과거 ingress-nginx)다.

**동작 원리**: 컨트롤러가 Ingress 객체를 감시하다가 자기 라우팅 설정을 갱신한다. 외부 요청은 컨트롤러가 받아 TLS를 풀고(TLS 종료) 경로에 맞는 Service로 넘긴다.

**ingress-nginx 은퇴**: 가장 널리 쓰이던 ingress-nginx 저장소가 2026년 3월 보관(archived)되어 보안 패치가 끝났다. 이 프로젝트는 GitHub API로 이를 확인하고 Traefik v3로 대체했다. 장기적으로는 **Gateway API**(Ingress 후속 표준: 인프라 담당은 Gateway, 앱 담당은 HTTPRoute로 역할 분리, TCP·gRPC 지원)로 옮기는 게 방향이다.

**이 프로젝트에서는**: `https://localhost/` → web-ui, `/api` → 게이트웨이, `/grafana`, `/sizing`. HTTP는 HTTPS로 301 리다이렉트. 게이트웨이의 `/metrics`·`/readyz`는 외부에 노출하지 않았다(404).

**면접 한 줄**: "Ingress는 L7 라우팅 규칙이고 컨트롤러가 실행하며, ingress-nginx 은퇴로 Traefik이나 Gateway API 구현체로 옮기는 추세입니다."

---

## 6.4 TLS와 인증서, 사설 CA

**정의**: TLS는 통신을 **암호화**하고, 접속한 서버가 **진짜인지 인증서로 확인**하는 프로토콜이다. HTTPS = HTTP + TLS.

**동작 원리 (간략한 핸드셰이크)**
1. 클라이언트가 접속하면 서버가 **인증서**(서버 이름, 공개키, 발급자 서명)를 보낸다.
2. 클라이언트는 발급자(CA)의 서명을 자기가 **신뢰하는 루트 CA 목록**으로 검증하고, 인증서의 이름(SAN)이 접속한 주소와 맞는지 확인한다.
3. 양쪽이 키 교환으로 **세션 키**를 만들고, 이후 통신은 그 키로 암호화한다.

**사설 CA**: 회사가 직접 운영하는 인증 기관이다. 사내 시스템 인증서를 발급하고, 직원 PC에 루트 인증서를 배포해 두면 브라우저가 신뢰한다. 폐쇄망 고객사는 보통 AD CS 같은 사내 CA가 있다.

**cert-manager**: 쿠버네티스에서 인증서를 자동 발급·갱신한다. 이 프로젝트는 자체 서명 부트스트랩 → 한빛정밀 루트 CA(10년, ECDSA) → `hanbit-ca` 발급자 → 서버 인증서(90일, 만료 15일 전 자동 갱신). `openssl s_client`로 `Verify return code: 0` 확인, CA 없이 접속하면 curl이 거부(exit 60).

**흔한 오해**: "자체 서명이면 암호화가 약하다" → 암호화 강도는 같다. 문제는 **신뢰**다. 클라이언트가 그 CA를 모르면 경고가 뜬다.

**실무 포인트**: 인증서 만료는 흔한 장애 원인이다(어느 날 갑자기 전체 접속 불가). 자동 갱신 + 만료 임박 알람이 필수다. 폐쇄망은 내부 NTP가 맞아야 인증서 유효 기간 검증이 된다.

**면접 한 줄**: "TLS는 암호화와 서버 인증을 함께 하고, 사내에서는 사설 CA로 발급한 인증서를 cert-manager로 자동 갱신하며 만료 알람을 겁니다."

---

## 6.5 NetworkPolicy

**정의**: Pod 사이의 통신 허용·차단 규칙이다. 라벨로 대상을 고르고, 들어오는(ingress)·나가는(egress) 방향별로 허용 목록을 쓴다.

**동작 원리**
- 쿠버네티스 기본값은 **모두 허용**이다. 어떤 Pod를 선택하는 정책이 하나라도 생기면, 그 Pod는 **정책에 적힌 것만** 허용된다(허용 목록 방식).
- 정책은 **CNI가 실제로 강제**한다. kind 기본 CNI(kindnet)는 정책을 무시해서 Calico를 썼다.
- 일반 설계: ① 네임스페이스 전체 **기본 거부**(`podSelector: {}`, Ingress·Egress) ② **DNS만 허용**(kube-dns:53) ③ 통신 지도대로 앱별 허용.

**이 프로젝트에서는**: 적용 전 연결 테스트 14개 중 **9개가 열려 있음**(채팅 화면이 DB에 직접 접근 가능, 라벨 없는 Pod가 DB·인터넷 접근 가능) → 적용 후 **14/14 기대대로**. 게이트웨이는 MinIO를 쓰지 않아 일부러 막았다(최소 권한). 적용 직후 수집 Job·헬스체크·권한 테스트로 기능 회귀를 확인했다.

**흔한 오해**
- "NetworkPolicy가 port-forward도 막는다" → port-forward는 API 서버 → kubelet → Pod로 들어가는 경로라 정책 대상이 아니다. RBAC(pods/portforward)로 통제한다.
- "라벨 기반이니 안전하다" → 같은 라벨로 Pod를 만들 수 있으면 우회된다. Pod 생성 권한(RBAC)과 Admission 정책이 함께 필요하다.

**면접 한 줄**: "NetworkPolicy는 기본이 모두 허용이라 네임스페이스에 기본 거부를 걸고 통신 지도대로 허용 목록을 만들며, CNI가 지원해야 실제로 막힙니다."

---

## 6.6 폐쇄망(에어갭) 구축

**정의**: 인터넷과 끊긴 내부망이다. 제조·금융·공공에 많다. 설치에 필요한 모든 것을 **사전에 반입**해야 한다.

**원칙**
1. 현장에서는 아무것도 인터넷에서 받지 않는다.
2. 버전과 해시를 고정하고, 반입 전후 **SHA256으로 변조·손상 여부**를 확인한다.
3. **반입 전에 같은 번들로 오프라인 리허설**을 한다(현장에서 파일 하나가 빠지면 반입 절차를 처음부터 다시 해야 함).

**반입 대상**: OS 패키지·드라이버, 컨테이너 이미지, 모델 파일, 매니페스트·차트, 데이터, 인증서 체계.

**이미지 반입의 함정 (이 프로젝트에서 실제로 겪음)**
| 문제 | 원인 | 교훈 |
|---|---|---|
| `content digest not found` | Docker Desktop(containerd 저장소)의 `docker save`가 **멀티 아키텍처 목차(index)**를 통째로 저장하는데 내용물은 amd64만 있음 | **반입 대상 아키텍처를 명시**(`--platform linux/amd64`) |
| digest 고정 이미지를 못 찾음 | 태그 없는 이미지는 tar에 이름이 안 남고, docker save가 목차를 다시 만들어 **digest가 바뀜** | 현장에서는 **내부 레지스트리에 push**(skopeo/crane)해야 digest가 보존된다 |
| 번들 목록 생성 실패 | 살아 있는 클러스터에서 목록을 읽음 | 설치 파일(차트·매니페스트)을 렌더링해 **선언적으로** 목록 생성 |

**멀티 아키텍처 이미지**: 하나의 이름(`busybox:1.36`) 아래 amd64·arm64 등 플랫폼별 이미지를 묶은 목차(manifest list / OCI index)가 있고, 노드가 자기 플랫폼 것을 골라 받는다.

**이 프로젝트 결과**: 번들 7.5GB(이미지 16종 4.3GB, 노드 이미지 0.4GB, 모델 2.9GB), 노드 iptables로 사설 대역 외 전부 차단 후 **15분 21초** 만에 전체 재구축, 인수 검증 통과.

**면접 한 줄**: "폐쇄망은 현장에서 아무것도 받지 않는다는 원칙으로 번들과 체크섬을 준비하고 사전에 오프라인 리허설을 하며, 이미지는 내부 레지스트리에 digest 그대로 올리는 게 정석입니다."

---

## 6.7 GPU 클러스터 네트워크 설계

**망 분리**
| 망 | 용도 | 대역(일반) |
|---|---|---|
| 관리망 | BMC(iDRAC/iLO), SSH, 모니터링 | 1~10GbE |
| 서비스망 | 사용자 요청, API | 25~100GbE |
| 스토리지망 | NFS·S3·병렬 파일시스템 | 100~400GbE |
| **GPU 연산망** | 학습 시 GPU 간 그래디언트 교환(All-Reduce) | 400~800Gb/s |

**RDMA**: CPU와 OS를 거치지 않고 다른 서버의 메모리에 직접 읽고 쓰는 기술이다. 지연과 CPU 부담이 크게 준다. GPUDirect RDMA는 GPU 메모리끼리 직접 주고받는다.

**InfiniBand vs RoCEv2**
| | InfiniBand | RoCEv2 |
|---|---|---|
| 정체 | RDMA 전용 네트워크 기술(NVIDIA Quantum 등) | 이더넷 위에서 RDMA (UDP/IP 캡슐화) |
| 장점 | 손실 없는 전송이 기본, 낮은 지연, 대규모 학습 검증 | 기존 이더넷 장비·운영 인력 활용 |
| 단점 | 전용 장비·인력, 비용 | **손실 없는 이더넷 설정**(PFC, ECN) 튜닝이 까다로움 |

**Spine-Leaf**: 서버가 붙는 Leaf(ToR) 스위치를 모든 Spine 스위치에 연결하는 2단 구조다. 어느 서버끼리든 경로(홉 수)가 같고, Spine을 늘려 대역을 키운다. GPU 연산망은 아래·위 대역 비율(오버서브스크립션)을 1:1로 설계한다. 서버당 GPU 수만큼 NIC를 두는 **rail-optimized** 구성도 쓴다.

**추론 vs 학습**: 추론 위주(이 프로젝트, M9 제안)는 서버 안에서 텐서 병렬을 하고 GPU 간 서버 간 통신이 적어 이더넷으로 충분한 경우가 많다. 대규모 학습은 GPU 연산망이 성능을 좌우한다.

**면접 한 줄**: "GPU 클러스터는 관리·서비스·스토리지·GPU 연산망을 분리하고, 학습용 연산망은 RDMA를 InfiniBand나 RoCEv2로 구성하며 Spine-Leaf로 확장합니다. 다만 실제 스위치 구성 경험은 없어서 공부로 이해한 수준입니다."
