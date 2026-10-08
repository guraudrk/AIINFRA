"""사이징 계산기 웹: https://localhost/sizing  (입구 경로 /sizing 아래에서 동작)"""
from datetime import date

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .calc import (GPUS, PRECISION_BYTES, as_dict, concurrent_requests_from_users, size_llm, size_ops,
                   size_vector_db)

app = FastAPI(title="AX Sizing", docs_url="/sizing/docs", openapi_url="/sizing/openapi.json")


class SizingIn(BaseModel):
    customer: str = "가상 고객사"
    params_b: float = Field(32, gt=0, le=1000)
    precision: str = "fp8"
    concurrent_users: int = Field(100, ge=1)
    active_ratio: float = Field(0.3, gt=0, le=1)
    context_tokens: int = Field(4096, ge=256)
    documents: int = Field(20000, ge=0)
    avg_pages: int = Field(10, ge=1)
    embed_dims: int = 1024
    daily_queries: int = Field(2000, ge=0)
    audit_retention_years: int = 1


def compute(p: SizingIn):
    conc = concurrent_requests_from_users(p.concurrent_users, p.active_ratio)
    llm = size_llm(p.params_b, p.precision, conc, p.context_tokens)
    vec = size_vector_db(p.documents, p.avg_pages, dims=p.embed_dims)
    ops = size_ops(p.daily_queries, db_gb=vec.total_gb, retention_years=p.audit_retention_years)
    return {"input": p.model_dump(), "concurrent_requests": conc, "llm": as_dict(llm),
            "vector_db": as_dict(vec), "ops": as_dict(ops)}


def to_markdown(r):
    i, llm, vec, ops = r["input"], r["llm"], r["vector_db"], r["ops"]
    rows = "\n".join(
        f"| {o['gpu']} | {o['tensor_parallel'] if o['fits'] else '서버 1대 초과'} | {o['per_gpu_gb']} / {o['usable_gb']} GB | {o['note']} |"
        for o in llm["options"])
    return f"""# AI 인프라 사이징 제안 (근사치) — {i['customer']}

> **이 수치는 공식 기반 근사치입니다.** 실제 구성은 고객 데이터·질문 세트로 PoC 벤치마크(TTFT, 처리량)를 측정해 확정합니다.
> 작성일 {date.today()} · AX Platform Lab 사이징 계산기

## 1. 입력 조건
| 항목 | 값 |
|---|---|
| 모델 | {i['params_b']}B, {i['precision'].upper()} |
| 동시 사용자 → 동시 생성 요청 | {i['concurrent_users']}명 × 활성 비율 {i['active_ratio']} → **{r['concurrent_requests']}건** |
| 요청당 컨텍스트 | {i['context_tokens']} 토큰 (RAG 근거 + 질문 + 답변) |
| 문서 | {i['documents']:,}건 × 평균 {i['avg_pages']}쪽, 임베딩 {i['embed_dims']}차원 |
| 일 질의 / 감사 로그 보관 | {i['daily_queries']:,}건 / {i['audit_retention_years']}년 |

## 2. LLM GPU 메모리
| 구성요소 | GB | 계산 |
|---|---|---|
| 가중치 | {llm['weights_gb']} | 파라미터 × {PRECISION_BYTES[i['precision']]}바이트 |
| KV 캐시 | {llm['kv_cache_gb']} | 2 × 레이어 × KV헤드 × 헤드차원 × 2바이트 × 컨텍스트 × 동시 요청 |
| 런타임 여유 (10%) | {llm['overhead_gb']} | 활성값·CUDA 컨텍스트·단편화 |
| **합계** | **{llm['total_gb']}** | |

| GPU | 텐서 병렬(장) | GPU당 사용 / 가용(90%) | 비고 |
|---|---|---|---|
{rows}

## 3. 벡터DB · 운영 데이터
| 항목 | 값 |
|---|---|
| 청크 수 | {vec['chunks']:,} |
| 벡터 / HNSW 인덱스 / 본문 | {vec['vector_gb']} / {vec['index_gb']} / {vec['text_gb']} GB |
| 벡터DB 합계 | **{vec['total_gb']} GB** (HNSW는 메모리 상주가 유리 → DB 서버 메모리에 반영) |
| 최초 임베딩 시간(CPU 실측 기준) | 약 {vec['embed_hours_cpu']}시간 → GPU 임베딩 서빙 시 크게 단축 |
| 감사 로그 | 연 {ops['audit_gb_per_year']} GB, 보관 기간 합계 {ops['audit_gb_retention']} GB |
| 백업(일 1회 × 7개, 압축 50%) | 약 {ops['backup_gb']} GB (+ 원본 문서·모델 파일 별도) |

## 4. 판단 기준 (온프레미스 GPU vs 클라우드 관리형 LLM API)
| 기준 | 온프레미스 GPU | 클라우드 LLM API |
|---|---|---|
| 보안·망분리 | 데이터가 사내에 머무름, 폐쇄망 가능 | 외부 전송 필요 → 폐쇄망·규제 산업에 제약 |
| 비용 구조 | 초기 투자(CAPEX) + 전력·운영, 사용량이 많을수록 유리 | 사용량 비례(OPEX), 초기 부담 낮음, 사용량 증가 시 비용 증가 |
| 확장성 | GPU 증설에 조달 리드타임 | 즉시 확장 |
| 모델 선택 | 공개 모델(sLLM) 중심, 직접 튜닝 가능 | 최신 대형 모델 사용 가능 |
| 운영 인력 | GPU·쿠버네티스·모델 운영 역량 필요 | 운영 부담 낮음 |
"""


@app.post("/sizing/api/calc")
def calc(p: SizingIn):
    return compute(p)


@app.post("/sizing/api/proposal.md", response_class=PlainTextResponse)
def proposal(p: SizingIn):
    return PlainTextResponse(to_markdown(compute(p)), headers={
        "Content-Disposition": "attachment; filename=sizing-proposal.md"})


@app.get("/sizing/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/sizing", response_class=HTMLResponse)
@app.get("/sizing/", response_class=HTMLResponse)
def page():
    gpu_list = ", ".join(f"{k} {v['mem_gb']}GB" for k, v in GPUS.items())
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AI 인프라 사이징</title>
<style>
:root{{--bg:#f4f6f7;--card:#fff;--ink:#17232b;--muted:#5a6b75;--line:#d6dee2;--accent:#0b6e8a;--warn:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#11181d;--card:#182229;--ink:#e3eaee;--muted:#94a6b0;--line:#2a3841;--accent:#4fb3cf;--warn:#f07a70}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Malgun Gothic",system-ui,sans-serif;font-size:15px}}
main{{max-width:1000px;margin:0 auto;padding:24px 16px;display:grid;gap:16px}}
h1{{margin:0;font-size:22px}} .muted{{color:var(--muted);font-size:13px}}
form{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;background:var(--card);border:1px solid var(--line);padding:14px}}
label{{display:grid;gap:4px;font-size:13px;color:var(--muted)}} input,select{{font:inherit;padding:6px 8px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}}
button{{font:inherit;padding:8px 14px;background:var(--accent);color:#fff;border:0;cursor:pointer}}
.out{{background:var(--card);border:1px solid var(--line);padding:14px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border-bottom:1px solid var(--line);padding:6px;text-align:left}}
.big{{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}} .warn{{color:var(--warn)}}
</style></head><body><main>
<h1>AI 인프라 사이징 계산기</h1>
<p class="muted">가중치 + KV 캐시 + 여유분 공식으로 GPU 대수를 근사합니다. GPU 목록: {gpu_list}. <b>모든 결과는 근사치</b>이며 PoC 벤치마크로 확정합니다.</p>
<form id="f">
<label>고객사<input id="customer" value="중견 자동차 부품 제조사"></label>
<label>모델 파라미터(B)<input id="params_b" type="number" step="0.5" value="32"></label>
<label>정밀도<select id="precision">{''.join(f'<option{" selected" if k == "fp8" else ""}>{k}</option>' for k in PRECISION_BYTES)}</select></label>
<label>동시 사용자(명)<input id="concurrent_users" type="number" value="100"></label>
<label>활성 비율(동시 생성 요청 / 동시 사용자)<input id="active_ratio" type="number" step="0.05" value="0.3"></label>
<label>요청당 컨텍스트(토큰)<input id="context_tokens" type="number" value="4096"></label>
<label>문서 수<input id="documents" type="number" value="20000"></label>
<label>문서당 평균 쪽수<input id="avg_pages" type="number" value="10"></label>
<label>임베딩 차원<input id="embed_dims" type="number" value="1024"></label>
<label>일 질의 수<input id="daily_queries" type="number" value="2000"></label>
<label>감사 로그 보관(년)<input id="audit_retention_years" type="number" value="1"></label>
<div style="display:flex;gap:8px;align-items:end"><button type="submit">계산</button><button type="button" id="md">제안서(.md) 받기</button></div>
</form>
<div class="out" id="out">계산 버튼을 누르면 결과가 나옵니다.</div>
</main><script>
const ids=["customer","params_b","precision","concurrent_users","active_ratio","context_tokens","documents","avg_pages","embed_dims","daily_queries","audit_retention_years"];
const body=()=>JSON.stringify(Object.fromEntries(ids.map(i=>{{const v=document.getElementById(i).value;return [i,(i==="customer"||i==="precision")?v:Number(v)]}})));
async function run(e){{e&&e.preventDefault();const r=await (await fetch("/sizing/api/calc",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:body()}})).json();
const l=r.llm,v=r.vector_db,o=r.ops;
document.getElementById("out").innerHTML=`<p>동시 생성 요청 <b>${{r.concurrent_requests}}건</b> 기준 LLM 메모리 <span class="big">${{l.total_gb}} GB</span>
 (가중치 ${{l.weights_gb}} + KV 캐시 ${{l.kv_cache_gb}} + 여유 ${{l.overhead_gb}})</p>
<table><tr><th>GPU</th><th>텐서 병렬</th><th>GPU당 사용/가용</th><th>비고</th></tr>${{l.options.map(x=>`<tr><td>${{x.gpu}}</td><td class="${{x.fits?"":"warn"}}">${{x.fits?x.tensor_parallel+"장":"서버 1대 초과"}}</td><td>${{x.per_gpu_gb}} / ${{x.usable_gb}} GB</td><td>${{x.note}}</td></tr>`).join("")}}</table>
<p>벡터DB: 청크 ${{v.chunks.toLocaleString()}}개, 약 <b>${{v.total_gb}} GB</b> (벡터 ${{v.vector_gb}} / 인덱스 ${{v.index_gb}} / 본문 ${{v.text_gb}}), 최초 임베딩 CPU 기준 약 ${{v.embed_hours_cpu}}시간</p>
<p>감사 로그 연 ${{o.audit_gb_per_year}} GB, 백업 약 ${{o.backup_gb}} GB · <span class="muted">근사치</span></p>`}}
document.getElementById("f").addEventListener("submit",run);
document.getElementById("md").addEventListener("click",async()=>{{const t=await (await fetch("/sizing/api/proposal.md",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:body()}})).text();
const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([t],{{type:"text/markdown"}}));a.download="sizing-proposal.md";a.click();}});
run();
</script></body></html>"""
