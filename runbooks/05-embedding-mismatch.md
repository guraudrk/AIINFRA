# 05. 임베딩 모델 교체 (차원 불일치)

> 재현: `make chaos SCENARIO=5` / 원복: `make chaos-revert SCENARIO=5`

## 증상
임베딩 모델 교체 후 모든 질문 오류.

## 영향
문서 검색 전체 실패 → 답변 불가

## 확인 명령 (실제 출력 일부)
```bash
kubectl -n ai-platform get deploy ax-gateway -o yaml | grep -A1 EMBED   # 바뀐 모델·주소
kubectl -n ai-platform logs deploy/llm-serving | grep /api/embed      # 501: 생성 모델은 임베딩 미지원 (실제 출력)
SELECT vector_dims(embedding) FROM chunks LIMIT 1;                    # 1024
#   ERROR: different vector dimensions 1024 and 768   <- 다른 차원 질문 벡터로 검색 시 실제 출력
```

## 원인
질문 임베딩 모델만 교체(문서는 재임베딩 안 함). 차원이 다르면 DB가 거부하고, 같아도 좌표계가 달라 검색 품질이 무너진다. 이번 재현에서는 생성 모델(qwen2.5:3b)을 임베딩에 지정해 501(미지원)로 먼저 실패했다

## 조치
임베딩 모델 원복. 교체가 목적이면 새 컬럼·새 테이블로 전체 재임베딩 후 전환 (블루/그린)

## 재발 방지
- 모델 이름과 차원을 함께 관리 (values의 dimensions)
- 수집 파이프라인 차원 검사 (적재 전 즉시 실패)
- 임베딩 모델 교체는 재수집 계획과 한 세트
