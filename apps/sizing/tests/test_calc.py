"""사이징 계산 검증: 손으로 계산 가능한 기준값으로 공식을 고정한다."""
import pytest

from sizing.calc import (concurrent_requests_from_users, kv_cache_gb, size_llm, size_ops,
                         size_vector_db, weights_gb)


def test_7b_fp16_weights_about_14gb():
    assert weights_gb(7, "fp16") == pytest.approx(14.0)


@pytest.mark.parametrize("precision,expected", [("fp8", 7.0), ("int8", 7.0), ("int4", 3.5)])
def test_quantization_halves_weights(precision, expected):
    assert weights_gb(7, precision) == pytest.approx(expected)


def test_kv_cache_matches_m2_calculation():
    # M2: qwen2.5:3b (36레이어, KV헤드 2, 헤드차원 128), 4096 컨텍스트 × 4슬롯 ≈ 0.6GB
    assert kv_cache_gb(36, 2, 128, 4096, 4) == pytest.approx(0.604, abs=0.01)


def test_kv_cache_scales_linearly_with_concurrency():
    assert kv_cache_gb(32, 8, 128, 4096, 20) == pytest.approx(2 * kv_cache_gb(32, 8, 128, 4096, 10))


def test_small_model_fits_one_gpu():
    r = size_llm(8, "fp16", concurrent=8, context_tokens=4096)
    assert all(o.fits and o.tensor_parallel == 1 for o in r.options)


def test_70b_fp16_needs_tensor_parallel():
    r = size_llm(70, "fp16", concurrent=16, context_tokens=4096)
    h100 = next(o for o in r.options if o.gpu == "H100-80G")
    assert r.weights_gb == pytest.approx(140.0)
    assert h100.tensor_parallel >= 2          # 80GB 한 장에 140GB 가중치는 불가능
    assert h100.per_gpu_gb <= h100.usable_gb


def test_fp8_on_a100_is_flagged():
    r = size_llm(32, "fp8", concurrent=8)
    a100 = next(o for o in r.options if o.gpu == "A100-80G")
    assert "FP8" in a100.note


def test_vector_db_m3_scale():
    # M3 실측: 문서 18개(평균 짧음) → 청크 138개. 공식은 문서 길이 가정에 따라 근사
    r = size_vector_db(20000, avg_pages=10)
    assert r.chunks == 20000 * 25            # 10쪽 × 1500자 / (700-100) = 25청크
    assert r.vector_gb == pytest.approx(500000 * 1024 * 4 / 1e9, rel=1e-3)
    assert r.total_gb > r.vector_gb


def test_ops_audit_and_backup():
    r = size_ops(daily_queries=2000, db_gb=10)
    assert r.audit_gb_per_year == pytest.approx(2000 * 365 * 1500 / 1e9, abs=0.01)  # 결과는 소수 둘째 자리 반올림
    assert r.backup_gb > 0


def test_users_to_concurrent_requests():
    assert concurrent_requests_from_users(100) == 30
    assert concurrent_requests_from_users(1) == 1
