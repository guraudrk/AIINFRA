# 00. 개발 환경 (M0 점검 결과, 2026-10-07)

## 호스트
| 항목 | 값 |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| CPU | AMD Ryzen 5 5600 (6코어 / 12스레드) |
| RAM | 15.9 GB (WSL에 12 GB 할당, `C:\Users\user\.wslconfig`: memory=12GB, swap=8GB) |
| GPU | NVIDIA GeForce RTX 4060, VRAM 8 GB, 드라이버 591.86 (CUDA 13.1 지원) |
| 디스크 (WSL /) | 1007 GB 중 955 GB 여유 |

## WSL / 도구 버전
| 도구 | 버전 | 비고 |
|---|---|---|
| WSL | 2.7.10, 커널 6.18.33.2-microsoft-standard-WSL2 | |
| 배포판 | Ubuntu 26.04 LTS | 사용자 lee1066515 |
| Docker | 29.6.1 (Docker Desktop, WSL Integration: Ubuntu ON) | 런타임에 `nvidia` 포함 |
| kubectl | v1.37.1 | /usr/local/bin, sha256 검증 |
| kind | v0.33.0 | /usr/local/bin |
| helm | v4.3.0 | /usr/local/bin |
| git | 2.53.0 | |
| python3 | 3.14.4 | |
| make | GNU Make 4.4.1 | apt |
| psql | 18.6 | apt postgresql-client |

## GPU 검증
| 확인 | 명령 | 결과 |
|---|---|---|
| WSL에서 드라이버 노출 | `nvidia-smi -L` | ✅ GPU 0: RTX 4060 (드라이버는 Windows에 설치, WSL은 `/usr/lib/wsl/lib`로 공유) |
| 컨테이너에서 GPU 사용 | `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` | ✅ 컨테이너 안에서 RTX 4060 인식 |
| 사용 가능한 VRAM | `nvidia-smi --query-gpu=memory.used,memory.total --format=csv` | ⚠️ 8188 MiB 중 약 5200 MiB를 Windows 화면·앱이 이미 사용 → **실제 여유 약 3 GB** |

## GPU 모드: **REAL** (조건부)
- Docker 레벨 GPU 사용은 검증 완료.
- kind 노드(컨테이너) 안까지 GPU를 노출해 device plugin이 `nvidia.com/gpu`를 광고하는지는 **M1에서 검증**한다.
  실패하거나 불안정하면 **SIMULATED**(fake-gpu.sh로 extended resource 패치)로 폴백하고, 이 표를 갱신한다.

## 추천 모델 크기
| 용도 | 추천 | 크기 근거 | 폴백 |
|---|---|---|---|
| sLLM | **Qwen2.5 3B Instruct** (Ollama `qwen2.5:3b`, Q4_K_M) | 3B × 약 0.5바이트(INT4) ≈ 1.5 GB + 오버헤드 → 약 1.9 GB. 여유 VRAM 3 GB 안에 들어감. 한국어 가능 | `qwen2.5:1.5b` (약 1 GB). CPU만으로도 동작 가능한 크기 |
| 임베딩 | **bge-m3** (Ollama `bge-m3`, 568M 파라미터, **1024차원**, 다국어) | FP16 기준 약 1.2 GB | CPU 실행 (임베딩은 수집 시 배치 처리라 느려도 무방) |

- 두 모델을 동시에 GPU에 올리면 약 3.1 GB → 여유 VRAM과 거의 같아서 빠듯하다. 브라우저 등을 닫아 VRAM을 확보하거나 임베딩은 CPU로 돌린다.
- CPU만 쓸 경우(6코어): 3B Q4는 대략 초당 수 토큰~10토큰 수준으로 예상(추정치). 실제 값은 M2의 `scripts/bench-llm.py`로 측정해 기록한다.
