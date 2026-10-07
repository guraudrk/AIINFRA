# 폐쇄망 설치 절차서 — 한빛정밀 사내 AI 플랫폼

> 대상: 인터넷이 차단된 고객사 현장에 AI 플랫폼을 설치하는 엔지니어
> 근거: 2026-10-07 로컬 리허설(kind 4노드, 노드 외부 통신 iptables 차단) 결과. 실제 현장은 OpenShift/RKE2 + 내부 레지스트리 구성을 가정하고 차이를 함께 적었다.

## 1. 원칙
1. **현장에서는 아무것도 인터넷에서 받지 않는다.** 설치에 필요한 모든 파일(이미지, 모델, 매니페스트, 차트, 데이터)을 사무실에서 번들로 만들어 반입한다.
2. **버전과 해시를 고정한다.** 태그(latest)가 아니라 정확한 버전·digest를 쓰고, 반입 전후 SHA256으로 변조·손상 여부를 확인한다.
3. **반입 전에 사무실에서 같은 번들로 오프라인 설치를 리허설한다.** 현장에서 "파일 하나가 없다"를 발견하면 반입 절차(승인·검사)를 처음부터 다시 해야 하기 때문이다.

## 2. 반입 체크리스트

### 2-1. 사전 확인 (고객사와 협의)
- [ ] 반입 매체와 절차: 보안 USB / 망연계 솔루션 / 반입 승인서, 백신 검사, 반입 가능 용량
- [ ] 서버 사양: CPU·메모리·GPU 모델과 수량, 디스크(번들 + 데이터 + 로그), OS 버전
- [ ] GPU 드라이버·CUDA 버전 호환표 (드라이버 ≥ CUDA 요구 버전)
- [ ] 내부 레지스트리 유무 (Harbor, Nexus, OpenShift 내장) → 없으면 노드 직접 적재(이번 리허설 방식)
- [ ] 사내 DNS 이름, 사내 CA(인증서 발급 주체), NTP 서버
- [ ] 방화벽: 관리망·서비스망 분리, 허용 포트(443, 관리 콘솔)
- [ ] 계정 체계: AD/LDAP 연동 여부, 문서 권한(ACL) 원천 시스템

### 2-2. 번들 구성 (`scripts/airgap-bundle.sh`)
| 구분 | 내용 | 크기(리허설) |
|---|---|---|
| 클러스터 노드 이미지 | kindest/node v1.37.0 (현장: OS ISO·RPM 저장소 미러) | 371 MB |
| 컨테이너 이미지 16종 | 플랫폼 앱 3종, Ollama(3.6 GB), PostgreSQL+pgvector, MinIO, Calico, cert-manager, Traefik, metrics-server 등 | 4.3 GB |
| 모델 | qwen2.5:3b(1.8 GB), bge-m3(1.1 GB) — PVC에서 추출한 Ollama 모델 디렉터리 | 2.9 GB |
| 설치 소스 | Helm 차트, 스크립트, vendor 매니페스트, 가상 데이터 (`git archive`) | 0.6 MB |
| **합계** | 파일 20개, SHA256 20줄 | **7.5 GB** |
| 무결성 | `MANIFEST.txt`(목록·버전), `SHA256SUMS` | – |

### 2-3. 현장 설치 순서 (`scripts/airgap-install.sh`)
| 단계 | 작업 | 확인 |
|---|---|---|
| 0 | 번들 SHA256 검증 | `sha256sum -c SHA256SUMS` 전부 OK |
| 1 | 클러스터 생성 | 노드 4대 생성 |
| 2 | 외부 통신 차단 확인 | 노드에서 외부 레지스트리 접속 실패 |
| 3 | 이미지 적재 | 큰 이미지(Ollama)는 GPU 노드에만 |
| 4 | CNI(Calico), metrics-server, GPU 리소스 | 노드 Ready, `nvidia.com/gpu: 2` |
| 5 | cert-manager → 사내 CA → Traefik | CA 인증서 Ready |
| 6 | 비밀값 생성 → 플랫폼 차트 | Secret 3종, Pod 생성 |
| 7 | **모델 복원** (반입 파일 → PVC) | 서빙 Pod Ready (`ollama show` 통과) |
| 8 | 데이터 수집 | 청크 138개 |
| 9 | 인수 검증 (`scripts/airgap-verify.sh`) | 아래 3장 |

## 3. 인수 검증 항목
- [ ] 노드·Pod에서 외부 인터넷 차단이 유지되는가
- [ ] 모든 Pod Running, CronJob 정상
- [ ] HTTPS 입구가 사내 CA로 검증되는가
- [ ] NetworkPolicy 허용·차단 표 전부 기대대로인가 (`netpol-test.sh`)
- [ ] 역할별 권한 테스트 전부 통과하는가 (`make test`)
- [ ] 고객 담당자와 결과 확인·서명

## 4. 리허설 결과 (2026-10-07, 2차 시도에서 성공)
| 단계 | 시작 시각(경과) | 소요 |
|---|---|---|
| 0. 번들 SHA256 검증 (7.5 GB) | 0초 | 227초 |
| 1. 클러스터 삭제·생성 | 227초 | 74초 |
| 2. 외부 통신 차단 확인 | 301초 | 11초 — 노드에서 registry-1.docker.io 접속 불가 ✅ |
| 3. 이미지 16종 적재 | 312초 | 314초 (Ollama 3.6 GB가 대부분) |
| 4. Calico·metrics-server·GPU | 626초 | 62초 |
| 5. cert-manager·사내 CA·Traefik | 688초 | 25초 |
| 6. 비밀값·플랫폼 차트 | 713초 | 32초 |
| 7. 모델 복원 (2.9 GB → PVC) | 745초 | 59초 |
| 8. 데이터 수집 (청크 138개) | 804초 | 117초 |
| **합계** | | **921초 (15분 21초)** |

**인수 검증** (`scripts/airgap-verify.sh`): 노드·Pod 외부 차단 유지 ✅, 모든 Pod 정상 ✅, HTTPS(사내 CA) ✅, NetworkPolicy 14/14 ✅, 권한 RAG 테스트 14/14 ✅

## 5. 리허설에서 발견한 문제와 대응
| # | 증상 | 원인 | 대응 | 현장 교훈 |
|---|---|---|---|---|
| 1 | 번들 생성 중 `error getting credentials` (반복) | WSL의 Docker CLI가 pull마다 Windows 자격 증명 도우미(desktop.exe)를 호출 → WSL interop(vsock) 시간 초과 | 번들 스크립트에서만 빈 `DOCKER_CONFIG`로 익명 pull | 공개 이미지만 받는다면 자격 증명이 필요 없다. 번들 작업 PC 환경을 미리 점검 |
| 2 | 이미지 적재 `content digest ... not found` | Docker Desktop(containerd 저장소)의 `docker save`가 **멀티 아키텍처 목차 전체**를 저장하지만 내용물은 amd64만 있음 → `ctr import --all-platforms` 실패 | `docker save --platform linux/amd64` | **반입 대상 아키텍처를 명시**해서 저장한다 (x86 서버 / ARM 서버 혼재 주의) |
| 3 | digest로 고정한 MinIO 이미지를 노드에서 찾지 못함 | 태그 없는 이미지는 tar에 이름이 안 남고, `docker save`가 목차를 다시 만들어 **digest가 바뀜** | 번들 생성 시 `pinned-<digest 8자리>` 태그를 붙여 저장, 설치 시 그 태그로 배포 (무결성은 0단계 SHA256으로 보장) | 실제 현장은 **내부 레지스트리에 push**해야 digest가 보존된다(skopeo/crane 사용). docker save는 digest 보존 수단이 아니다 |
| 4 | 1차 시도 후 번들 재생성 실패 | 번들 스크립트가 "살아 있는 클러스터"에서 이미지·모델 목록을 읽음 | **차트·vendor 매니페스트를 렌더링**해서 image: 목록 생성 (클러스터 불필요) | 반입 목록은 설치 파일에서 선언적으로 뽑아야 누락이 없다 |
| 5 | 인수 검증에서 감사 로그 테스트 1건 실패 | 테스트가 실행 순서·과거 기록(최근 30분)에 의존 → 새 DB에서 0건 | 테스트가 직접 만든 요청의 기록만 확인하도록 수정 | 깨끗한 환경에서 재설치해 보면 숨은 의존이 드러난다 |

## 6. 운영 전환 전 후속 과제 (비밀값 점검 결과)
- [ ] etcd 저장 암호화(EncryptionConfiguration) 또는 외부 비밀 관리(Vault, External Secrets) — 현재 Secret은 base64 저장
- [ ] 쿠버네티스 API를 쓰지 않는 Pod는 `automountServiceAccountToken: false` (현재 10개 Pod 전부 자동 마운트)
- [ ] MinIO 루트 사용자 이름도 무작위화, 앱별 MinIO 계정·정책 분리 (현재 수집이 루트 계정 사용)
- [ ] 데모 공유 비밀번호 → 사내 SSO(OIDC) 연동

## 7. 실제 현장과의 차이
| 항목 | 리허설(kind) | 실제 현장 |
|---|---|---|
| 폐쇄망 구현 | 노드 iptables로 사설망 외 DROP | 물리적 망분리, 방화벽 |
| 이미지 배포 | `kind load image-archive`로 노드마다 직접 적재 | **내부 레지스트리**(Harbor 등)에 push 후 미러 설정 |
| 모델 배포 | tar를 PVC에 `kubectl exec`로 풀기 | 내부 오브젝트 스토리지(MinIO)·모델 레지스트리에서 다운로드, 버전 관리 |
| OS·드라이버 | kind 노드 이미지에 포함 | OS 저장소 미러, NVIDIA 드라이버 패키지(또는 GPU Operator 드라이버 컨테이너) |
| 인증서 | 자체 서명 루트 CA | 고객사 사내 CA(AD CS 등)에서 발급 |
| 시간 | NTP 불필요(호스트 시간) | 내부 NTP 필수 (인증서·로그 시각) |
