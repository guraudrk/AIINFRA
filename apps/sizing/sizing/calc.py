"""AI 인프라 사이징 계산 (근사치).

LLM GPU 메모리 = 가중치 + KV 캐시 + 런타임 여유
  가중치    = 파라미터 수 × 파라미터당 바이트 (FP16 2 / FP8·INT8 1 / INT4 0.5)
  KV 캐시   = 2(K,V) × 레이어 × KV헤드 × 헤드차원 × KV바이트 × 컨텍스트 × 동시 요청
  여유      = (가중치 + KV) × 10%  (활성값·CUDA 컨텍스트·단편화)
GPU는 메모리의 90%만 쓴다고 본다 (vLLM gpu_memory_utilization 0.9 관례).
"""
import math
from dataclasses import dataclass, asdict

GB = 1e9

PRECISION_BYTES = {"fp16": 2.0, "bf16": 2.0, "fp8": 1.0, "int8": 1.0, "int4": 0.5}

# 데이터센터 GPU (메모리 GB, FP8 지원, 같은 서버 GPU 간 고속 연결)
GPUS = {
    "L40S": {"mem_gb": 48, "fp8": True, "nvlink": False, "note": "PCIe, 추론·그래픽 겸용, 서버당 4~8장"},
    "A100-80G": {"mem_gb": 80, "fp8": False, "nvlink": True, "note": "Ampere, FP8 미지원(INT8은 가능)"},
    "H100-80G": {"mem_gb": 80, "fp8": True, "nvlink": True, "note": "Hopper, NVLink, 대형 모델 텐서 병렬에 적합"},
    "H200-141G": {"mem_gb": 141, "fp8": True, "nvlink": True, "note": "Hopper, 대용량 HBM3e → 긴 컨텍스트·큰 KV 캐시"},
}

# 대표 모델 구조 (GQA 기준 근사): 파라미터(B) → (레이어, KV헤드, 헤드차원)
ARCH_PRESETS = [
    (3, (36, 2, 128)),     # Qwen2.5-3B 류
    (8, (32, 8, 128)),     # 7~8B (Llama-3-8B, Qwen2.5-7B 류)
    (14, (48, 8, 128)),    # 14B
    (32, (64, 8, 128)),    # 32B
    (72, (80, 8, 128)),    # 70B급
]

USABLE_RATIO = 0.9
OVERHEAD_RATIO = 0.10


def arch_for(params_b):
    """파라미터 수에 가장 가까운 대표 구조."""
    return min(ARCH_PRESETS, key=lambda p: abs(p[0] - params_b))[1]


def weights_gb(params_b, precision):
    return params_b * 1e9 * PRECISION_BYTES[precision] / GB


def kv_cache_gb(layers, kv_heads, head_dim, context_tokens, concurrent, kv_bytes=2.0):
    per_token = 2 * layers * kv_heads * head_dim * kv_bytes
    return per_token * context_tokens * concurrent / GB


@dataclass
class GpuOption:
    gpu: str
    tensor_parallel: int      # 모델 한 벌을 몇 장에 나눠 올리는가 (1, 2, 4, 8)
    per_gpu_gb: float         # GPU 한 장이 짊어지는 메모리
    usable_gb: float
    fits: bool
    note: str


@dataclass
class LLMSizing:
    params_b: float
    precision: str
    concurrent: int
    context_tokens: int
    weights_gb: float
    kv_cache_gb: float
    overhead_gb: float
    total_gb: float
    options: list


def size_llm(params_b, precision="fp16", concurrent=8, context_tokens=4096, arch=None):
    layers, kv_heads, head_dim = arch or arch_for(params_b)
    w = weights_gb(params_b, precision)
    kv = kv_cache_gb(layers, kv_heads, head_dim, context_tokens, concurrent)
    oh = (w + kv) * OVERHEAD_RATIO
    total = w + kv + oh
    options = []
    for name, g in GPUS.items():
        usable = g["mem_gb"] * USABLE_RATIO
        tp = 1
        while tp <= 8 and total / tp > usable:     # 텐서 병렬은 2의 거듭제곱, 한 서버 최대 8장
            tp *= 2
        fits = tp <= 8
        note = g["note"]
        if precision == "fp8" and not g["fp8"]:
            note += " / ⚠ FP8 연산 미지원 → INT8 또는 FP16 필요"
        if fits and tp > 1 and not g["nvlink"]:
            note += " / PCIe 텐서 병렬은 GPU 간 통신 병목 가능"
        if not fits:
            note += " / 서버 1대(8장)로 부족 → 다중 노드 또는 양자화·컨텍스트 축소"
        options.append(GpuOption(name, tp if fits else 0, round(total / min(tp, 8), 1), round(usable, 1), fits, note))
    return LLMSizing(params_b, precision, concurrent, context_tokens,
                     round(w, 1), round(kv, 1), round(oh, 1), round(total, 1), options)


@dataclass
class VectorSizing:
    documents: int
    chunks: int
    vector_gb: float
    index_gb: float
    text_gb: float
    total_gb: float
    embed_hours_cpu: float


def size_vector_db(documents, avg_pages=10, chars_per_page=1500, chunk_chars=700, overlap_chars=100,
                   dims=1024, hnsw_m=16, embed_chunks_per_sec=2.2):
    """벡터DB 용량: 청크 수 × 차원 × 4바이트(float32) + HNSW 링크 + 본문(UTF-8 한글 3바이트).
    embed_chunks_per_sec 기본값 2.2는 M3 실측(CPU, bge-m3, 138청크 63초)."""
    per_doc = math.ceil(avg_pages * chars_per_page / (chunk_chars - overlap_chars))
    chunks = documents * per_doc
    vec = chunks * dims * 4 / GB
    index = vec + chunks * hnsw_m * 2 * 8 / GB          # 이웃 링크(층 0에서 2m개) 근사
    text = chunks * chunk_chars * 3 / GB
    return VectorSizing(documents, chunks, round(vec, 2), round(index, 2), round(text, 2),
                        round(vec + index + text, 2), round(chunks / embed_chunks_per_sec / 3600, 1))


@dataclass
class OpsSizing:
    daily_queries: int
    audit_gb_per_year: float
    audit_gb_retention: float
    backup_gb: float


def size_ops(daily_queries, db_gb, audit_row_bytes=1500, retention_years=1, backup_copies=7, compression=0.5):
    """감사 로그(질문·사용 문서·도구·결과 1행 약 1.5KB)와 백업(일 1회 × 보관 개수 × 압축률) 용량."""
    per_year = daily_queries * 365 * audit_row_bytes / GB
    audit_ret = per_year * retention_years
    backup = (db_gb + audit_ret) * compression * backup_copies
    return OpsSizing(daily_queries, round(per_year, 2), round(audit_ret, 2), round(backup, 1))


def concurrent_requests_from_users(concurrent_users, active_ratio=0.3):
    """'동시 사용자'는 화면을 열어 둔 사람 수다. 실제로 같은 순간 생성 중인 요청은 그 일부(기본 30%)."""
    return max(1, math.ceil(concurrent_users * active_ratio))


def as_dict(obj):
    return asdict(obj)
