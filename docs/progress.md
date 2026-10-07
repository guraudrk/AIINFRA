# 진행 상황

> "이어서 하자"라고 하면 이 파일을 먼저 읽고 이어서 진행한다.

## 마지막 작업일: 2026-10-07 (수)
- 면접: **2026-10-14 (수)**, 에티버스이피에이 AI 시스템 엔지니어 실무면접
- 남은 일정 계획: 10/8(목), 10/12(월), 10/13(화)에 M5~M10 (하루 2모듈)

## 모듈 상태 (전체 약 60%)
| 모듈 | 상태 | 커밋 | 핵심 결과 |
|---|---|---|---|
| M0 환경 | ✅ | 5e2f09b | WSL2 12GB, Docker GPU 검증, 도구 설치 |
| M1 클러스터 | ✅ | d3fb05b | kind 4노드, Calico, GPU SIMULATED(2개), 배치 검증 |
| M2 LLM 서빙 | ✅ | 09050e0 | qwen2.5:3b + bge-m3, CPU 벤치(동시 4개 34.8 토큰/s) |
| M3 데이터 | ✅ | 084132a | 가상 문서 18개 → 청크 138개, pgvector, MinIO(Chainguard) |
| M4 권한 RAG ★ | ✅ | 8095bcc | 역할 4 × 도구 4, 앱 필터 + RLS, 자동 테스트 14/14 |
| M5 네트워크·폐쇄망 | ✅ | b05b193 | Traefik+TLS, NetworkPolicy 14/14, 폐쇄망 재구축 15분 21초 |
| M6 모니터링 | ⬜ 다음 | | |
| M7 백업·복구 | ⬜ | | |
| M8 장애 대응 ★ | ⬜ | | 장애만 일으키고 멈춤, 원인은 사용자가 직접 찾음 |
| M9 사이징·제안 | ⬜ | | |
| M10 마무리·모의면접 | ⬜ | | |

## 다시 시작할 때
1. 사용자 요청: **먼저 지금까지(특히 M5: 정문·출입 통제·폐쇄망 반입)를 비유(클러스터 = 병원) 중심으로 쉽게 정리**해 주고 M6으로 넘어간다.
2. 클러스터 상태 점검: `make status` — PC나 Docker Desktop을 재시작했다면 kind 노드·Pod 복구부터 확인한다.
3. 프롬프트집 "프롬프트 7 — M6"부터 진행한다.
4. 참고: M5 폐쇄망 리허설로 클러스터를 다시 만들어 **Secret이 새로 생성됨**(데모 비밀번호·CA 변경). 노드 인터넷 차단은 해제한 상태(`block-egress.sh`로 다시 걸 수 있음).

## 사용자가 직접 할 일 (남아 있음)
- [ ] `docs/study/04-rag-agent.md` Q4의 **[✏️ 직접 채우기]** — ERP 권한 표준화 전 상황 (본인 경험)
- [ ] 캡처 → `docs/images/`: m1-nodes, m2-hallucination, m3-search, m3-minio, **m4-worker/maint/quality/admin**
- [ ] GitHub 연동 (사용자가 별도로 진행 예정)

## 환경 메모 (재발 방지)
- Claude는 Windows에서 실행되고 WSL은 `wsl.exe -d Ubuntu -e bash -lc`로 다룬다. 파일은 `\\wsl.localhost\Ubuntu\home\lee1066515\ax-platform-lab`.
- Windows 쪽에서 스크립트를 편집하면 실행 권한이 빠진다 → `chmod +x scripts/*.sh scripts/*.py`
- `wsl --shutdown`을 하면 Docker Desktop 엔진도 꺼진다 → Docker Desktop을 재시작해야 한다.
- Helm이 관리하는 리소스를 `kubectl set/edit`로 고치지 않는다(Helm 4 SSA 충돌). 바꿀 때는 `helm upgrade --set`.
- 비밀값은 Secret에만 있다: postgres-credentials, minio-credentials, gateway-secrets (`make secrets`, 이미 있으면 유지).
