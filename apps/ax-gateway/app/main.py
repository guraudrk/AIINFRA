"""ax-gateway: 한빛정밀 권한 기반 사내 AI 게이트웨이.

흐름: 로그인(JWT) → 질문 해석(설비·경보 코드·의도) → 도구 실행(역할별 허용) → 근거로 LLM 요약 → 출처·감사 로그

권한 통제 두 겹
  (a) 앱: search_docs 가 역할에 허용된 access_level 만 검색 (APP_FILTER_ENABLED)
  (b) DB: 요청마다 트랜잭션에 app.role 을 설정하고, PostgreSQL RLS 정책이 행 자체를 숨긴다
"""
import hmac
import json
import os
import re
import time
import urllib.request
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

# ── 설정 ─────────────────────────────────────────────────────
LLM_URL = os.environ.get("LLM_URL", "http://llm-serving:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b")
EMBED_URL = os.environ.get("EMBED_URL", "http://embedding-serving:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
JWT_SECRET = os.environ["JWT_SECRET"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]
APP_FILTER_ENABLED = os.environ.get("APP_FILTER_ENABLED", "true").lower() == "true"
AGENT_MODE = os.environ.get("AGENT_MODE", "rules")      # rules | llm
TOP_K = int(os.environ.get("TOP_K", "4"))
MAX_DISTANCE = float(os.environ.get("MAX_DISTANCE", "0.5"))  # 이보다 먼 청크는 근거로 쓰지 않음

DB_CONNINFO = (f"host={os.environ.get('PGHOST', 'postgres')} dbname={os.environ.get('PGDATABASE', 'hanbit')} "
               f"user={os.environ.get('PGUSER', 'ax_app')} password={os.environ['PGPASSWORD']} connect_timeout=5")

# 데모 사용자 (가상). 비밀번호는 Secret 의 DEMO_PASSWORD 하나를 공유한다
USERS = {
    "worker01": {"name": "생산팀 작업자", "role": "worker", "dept": "생산팀"},
    "maint01": {"name": "설비보전팀 정비원", "role": "maintenance", "dept": "설비보전팀"},
    "quality01": {"name": "품질팀 담당자", "role": "quality", "dept": "품질팀"},
    "admin01": {"name": "공장 관리자", "role": "admin", "dept": "경영지원팀"},
}
# 역할 → 볼 수 있는 문서 등급 (DB RLS 함수 app_allowed_levels() 와 같은 규칙을 일부러 따로 둔다)
ROLE_LEVELS = {
    "worker": ["public"],
    "maintenance": ["public", "maintenance"],
    "quality": ["public", "quality"],
    "admin": ["public", "maintenance", "quality", "admin"],
}
TOOL_ROLES = {
    "search_docs": {"worker", "maintenance", "quality", "admin"},
    "query_maintenance": {"maintenance", "admin"},
    "check_stock": {"maintenance", "admin"},
    "draft_ticket": {"worker", "maintenance", "quality", "admin"},
}
TOOL_LABELS = {"query_maintenance": "정비 이력 조회", "check_stock": "부품 재고 확인"}

# ── 지표 (/metrics) ──────────────────────────────────────────
REQUESTS = Counter("ax_requests_total", "채팅 요청 수", ["role", "result"])
LATENCY = Histogram("ax_request_duration_seconds", "채팅 응답 시간", buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300))
LLM_LATENCY = Histogram("ax_llm_duration_seconds", "LLM 호출 시간", buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300))
TOOL_CALLS = Counter("ax_tool_calls_total", "도구 호출 수", ["tool"])
DENIED = Counter("ax_permission_denied_total", "권한 거부 수", ["role", "tool"])
SEARCHES = Counter("ax_search_total", "문서 검색 수", ["role"])
SEARCH_EMPTY = Counter("ax_search_empty_total", "근거 0건 검색 수", ["role"])

pool = ConnectionPool(DB_CONNINFO, min_size=1, max_size=5, open=False,
                      check=ConnectionPool.check_connection)  # 끊긴 연결은 꺼내기 전에 검사 후 교체


@asynccontextmanager
async def lifespan(_app):
    pool.open(wait=False)  # DB가 아직 없어도 앱은 뜨고, readiness 가 DB 연결을 확인한다
    yield
    pool.close()


app = FastAPI(title="ax-gateway", lifespan=lifespan)


@contextmanager
def db_session(role):
    """요청 단위 트랜잭션. set_config(..., true) = 이 트랜잭션에서만 유효 → 연결을 재사용해도 역할이 새지 않는다."""
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.role', %s, true)", (role,))
            conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")  # 필터 때문에 결과가 모자라면 더 탐색
            yield conn


# ── 인증 ─────────────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str


class ChatIn(BaseModel):
    question: str


def current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "토큰이 유효하지 않습니다")


@app.post("/api/login")
def login(body: LoginIn):
    user = USERS.get(body.username)
    if not user or not hmac.compare_digest(body.password, DEMO_PASSWORD):
        raise HTTPException(401, "아이디 또는 비밀번호가 틀렸습니다")
    claims = {"sub": body.username, **user, "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return {"token": jwt.encode(claims, JWT_SECRET, algorithm="HS256"), "user": {"id": body.username, **user}}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


# ── 외부 호출 ────────────────────────────────────────────────
def post_json(url, payload, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def embed(text):
    return post_json(f"{EMBED_URL}/api/embed", {"model": EMBED_MODEL, "input": text})["embeddings"][0]


def llm_chat(messages, tools=None):
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False,
               "options": {"temperature": 0.1, "num_predict": 350}}
    if tools:
        payload["tools"] = tools
    start = time.perf_counter()
    try:
        return post_json(f"{LLM_URL}/api/chat", payload)["message"]
    finally:
        LLM_LATENCY.observe(time.perf_counter() - start)


# ── 질문 해석 (규칙 기반) ─────────────────────────────────────
ALARM_RE = re.compile(r"E\s*-?\s*(\d{3})", re.IGNORECASE)
UNIT_RE = re.compile(r"(\d)\s*호기")


def parse_question(conn, q):
    """설비 종류·호기·경보 코드를 뽑는다. 종류가 없으면 경보 코드가 어느 설비 종류에 있는지 DB(온톨로지)로 판단."""
    code = f"E-{m.group(1)}" if (m := ALARM_RE.search(q)) else None
    eq_type = "cnc" if "CNC" in q.upper() else "press" if "프레스" in q else None
    if not eq_type and code:
        types = [r[0] for r in conn.execute("SELECT equipment_type FROM alarm_codes WHERE code = %s", (code,))]
        eq_type = types[0] if len(types) == 1 else None
    unit = m.group(1) if (m := UNIT_RE.search(q)) else None
    equipment_id = f"{'CNC' if eq_type == 'cnc' else 'PRESS'}-0{unit}" if unit and eq_type else None
    return {
        "equipment_id": equipment_id, "equipment_type": eq_type, "alarm_code": code,
        "wants_history": any(k in q for k in ("이력", "최근", "기록", "언제")),
        "wants_stock": any(k in q for k in ("재고", "부품", "자재")),
        "wants_ticket": any(k in q for k in ("요청", "접수", "티켓", "신고")),
    }


# ── 도구 4개 ─────────────────────────────────────────────────
KEYWORD_BONUS = 0.1     # 경보 코드가 본문에 그대로 있으면 거리에서 빼 주는 가산점
RELATIVE_CUTOFF = 0.1   # 1등보다 이만큼 이상 먼 청크는 버림 (관련 없는 섹션이 끼는 것 방지, 실측으로 조정)


def tool_search_docs(conn, role, query, equipment_id=None, alarm_code=None):
    """하이브리드 검색: 벡터로 후보를 넉넉히 뽑고 → 경보 코드 키워드로 재정렬 → 거리 기준으로 거른다."""
    level_filter = "AND c.access_level = ANY(%(levels)s)" if APP_FILTER_ENABLED else ""  # (a) 앱 권한 필터
    rows = conn.execute(f"""
        SELECT c.doc_id, d.version, d.title, c.section, c.access_level, c.content,
               c.embedding <=> %(vec)s::vector AS distance
        FROM chunks c JOIN documents d USING (doc_id)
        WHERE TRUE {level_filter}
          AND (%(eq)s::text IS NULL OR d.equipment_id IS NULL OR d.equipment_id = %(eq)s)
        ORDER BY c.embedding <=> %(vec)s::vector
        LIMIT %(k)s""",
        {"vec": "[" + ",".join(map(str, embed(query))) + "]", "levels": ROLE_LEVELS[role],
         "eq": equipment_id, "k": TOP_K * 3}).fetchall()
    keys = ("doc_id", "version", "title", "section", "access_level", "content", "distance")
    cands = [dict(zip(keys, r)) for r in rows if r[6] <= MAX_DISTANCE]
    for c in cands:
        c["score"] = c["distance"] - (KEYWORD_BONUS if alarm_code and alarm_code in c["content"] else 0)
    cands.sort(key=lambda c: c["score"])
    if not cands:
        return []
    best = cands[0]["score"]
    return [c for c in cands if c["score"] <= best + RELATIVE_CUTOFF][:TOP_K]


def tool_query_maintenance(conn, equipment_id, alarm_code=None, limit=5):
    if not equipment_id:
        return {"error": "설비(예: 3호기)를 특정할 수 없어 정비 이력을 조회하지 않았습니다"}
    rows = conn.execute("""
        SELECT work_date, alarm_code, work_type, description, parts_used, downtime_min
        FROM maintenance_history
        WHERE equipment_id = %s AND (%s::text IS NULL OR alarm_code = %s)
        ORDER BY work_date DESC LIMIT %s""", (equipment_id, alarm_code, alarm_code, limit)).fetchall()
    return [{"date": str(r[0]), "alarm": r[1], "type": r[2], "desc": r[3], "parts": r[4], "downtime_min": r[5]}
            for r in rows]


def tool_check_stock(conn, equipment_type, alarm_code):
    if not (equipment_type and alarm_code):
        return {"error": "설비 종류와 경보 코드가 있어야 필요 부품을 찾을 수 있습니다"}
    rows = conn.execute("""
        SELECT p.part_no, p.name, s.qty, s.min_qty, s.location
        FROM alarm_parts ap JOIN parts p USING (part_no) JOIN stock s USING (part_no)
        WHERE ap.equipment_type = %s AND ap.code = %s ORDER BY p.part_no""",
        (equipment_type, alarm_code)).fetchall()
    return [{"part_no": r[0], "name": r[1], "qty": r[2], "min_qty": r[3], "location": r[4],
             "status": "재고 없음" if r[2] == 0 else "부족" if r[2] < r[3] else "충분"} for r in rows]


PRIORITY = {"critical": "30분 이내", "high": "2시간 이내", "medium": "당일", "low": "주간"}


def tool_draft_ticket(conn, user, parsed, question):
    """정비 요청 절차(REG-MAINT-REQ)의 필수 항목으로 요청서 초안을 만든다. 저장은 하지 않는다(초안)."""
    row = None
    if parsed["equipment_type"] and parsed["alarm_code"]:
        row = conn.execute("SELECT title, severity FROM alarm_codes WHERE equipment_type = %s AND code = %s",
                           (parsed["equipment_type"], parsed["alarm_code"])).fetchone()
    return {"equipment_id": parsed["equipment_id"] or "(확인 필요)", "alarm_code": parsed["alarm_code"] or "(확인 필요)",
            "alarm_title": row[0] if row else None, "severity": row[1] if row else None,
            "target_response": PRIORITY.get(row[1], "당직자 판단") if row else "당직자 판단",
            "occurred_at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
            "symptom": question, "requester": f"{user['name']} ({user['sub']})", "production_impact": "(작성 필요)"}


# ── 계획 수립 ────────────────────────────────────────────────
def plan_rules(role, parsed):
    """규칙 기반: 질문 의도와 역할로 도구를 고른다. 결과가 일정하고 3B 모델에서도 안정적이다."""
    tools = ["search_docs"]
    if parsed["wants_history"]:
        tools.append("query_maintenance")
    if parsed["wants_stock"] or (parsed["alarm_code"] and role in ("maintenance", "admin")):
        tools.append("check_stock")
    if parsed["wants_ticket"] or (parsed["alarm_code"] and role == "worker"):
        tools.append("draft_ticket")   # 작업자의 다음 행동은 정비 요청이다
    return tools


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": n, "description": d, "parameters": {"type": "object", "properties": {}}}}
    for n, d in [("search_docs", "사내 문서(매뉴얼·규정·보고서)에서 관련 내용을 검색한다"),
                 ("query_maintenance", "특정 설비의 최근 정비 이력을 조회한다"),
                 ("check_stock", "경보 코드 조치에 필요한 부품의 재고를 확인한다"),
                 ("draft_ticket", "설비보전팀에 보낼 정비 요청서 초안을 만든다")]
]


def plan_llm(question):
    """LLM 도구 호출: 모델이 도구를 고른다. 인자는 규칙 파서 값을 쓴다(3B 모델의 인자 오류를 줄이기 위해)."""
    msg = llm_chat([{"role": "system", "content": "질문에 답하는 데 필요한 도구를 모두 호출하라."},
                    {"role": "user", "content": question}], tools=TOOL_SCHEMAS)
    names = [c["function"]["name"] for c in msg.get("tool_calls") or [] if c["function"]["name"] in TOOL_ROLES]
    return list(dict.fromkeys(["search_docs", *names]))  # 검색은 항상 포함, 중복 제거


# ── 답변 생성 ────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "너는 한빛정밀 사내 설비 지원 AI다. 반드시 [자료]에 있는 내용만 근거로 한국어로 답한다. "
    "자료에 없는 내용은 추측하지 말고 '제공된 자료에서 찾을 수 없습니다'라고 말한다. "
    "각 문장 끝에 근거 자료 번호를 [1]처럼 붙인다. 6~10줄 이내로 간결하게, 조치는 번호 목록으로 쓴다."
)


ROLE_HINTS = {
    "worker": "질문자는 생산 현장 작업자다. 작업자가 직접 할 수 있는 안전 조치와 정비 요청 방법 위주로 답하고, 분해·수리 방법은 안내하지 않는다.",
    "maintenance": "질문자는 설비보전팀 정비원이다. 원인별 점검·조치 순서와 정비 이력, 필요 부품 재고를 구체적으로 답한다.",
    "quality": "질문자는 품질팀 담당자다. 품질 영향, 불량 사례, 재발 방지 조치 위주로 답한다.",
    "admin": "질문자는 공장 관리자다. 설비 조치, 정비 이력, 품질 영향을 종합해 요약한다.",
}


def build_context(docs, results):
    parts, n = [], 1
    for d in docs:
        parts.append(f"[{n}] 문서 {d['doc_id']} v{d['version']} ({d['title']} > {d['section']})\n{d['content']}")
        n += 1
    for tool, data in results.items():
        if tool == "search_docs":
            continue
        parts.append(f"[{n}] 도구 {tool} 결과\n{json.dumps(data, ensure_ascii=False)}")  # 들여쓰기 없이 → 토큰 절약
        n += 1
    return "\n\n".join(parts)


@app.post("/api/chat")
def chat(body: ChatIn, user=Depends(current_user)):
    start = time.perf_counter()
    role, question = user["role"], body.question.strip()
    tools_used, denied, docs, results, outcome = [], [], [], {}, "error"
    answer, parsed = "", {}
    try:
        with db_session(role) as conn:
            parsed = parse_question(conn, question)
            plan = plan_llm(question) if AGENT_MODE == "llm" else plan_rules(role, parsed)
            for tool in plan:
                if role not in TOOL_ROLES[tool]:      # 도구 단위 권한 검사
                    denied.append(tool)
                    DENIED.labels(role, tool).inc()
                    continue
                TOOL_CALLS.labels(tool).inc()
                tools_used.append(tool)
                if tool == "search_docs":
                    SEARCHES.labels(role).inc()
                    docs = tool_search_docs(conn, role, question, parsed["equipment_id"], parsed["alarm_code"])
                    if not docs:
                        SEARCH_EMPTY.labels(role).inc()
                    results[tool] = [d["doc_id"] for d in docs]
                elif tool == "query_maintenance":
                    results[tool] = tool_query_maintenance(conn, parsed["equipment_id"], parsed["alarm_code"])
                elif tool == "check_stock":
                    results[tool] = tool_check_stock(conn, parsed["equipment_type"], parsed["alarm_code"])
                elif tool == "draft_ticket":
                    results[tool] = tool_draft_ticket(conn, user, parsed, question)

        # 문서뿐 아니라 도구 결과(정비 이력·재고·요청서 초안)도 근거로 인정한다
        has_evidence = docs or any(v and not (isinstance(v, dict) and "error" in v)
                                   for k, v in results.items() if k != "search_docs")
        if not has_evidence:
            # 근거가 없으면 LLM을 부르지 않는다 → 그럴듯한 지어내기(환각)를 원천 차단
            answer = "제공된 자료에서 근거를 찾을 수 없습니다. 질문을 구체적으로(설비 호기, 경보 코드) 다시 해 주시거나 설비보전팀(내선 3200)에 문의해 주세요."
            outcome = "unknown"
        else:
            msg = llm_chat([{"role": "system", "content": SYSTEM_PROMPT + " " + ROLE_HINTS[role]},
                            {"role": "user", "content": f"[자료]\n{build_context(docs, results)}\n\n[질문]\n{question}"}])
            answer = msg["content"].strip()
            outcome = "answered"
        if denied:
            answer += ("\n\n※ 권한이 없어 실행하지 않은 기능: " + ", ".join(TOOL_LABELS.get(t, t) for t in denied)
                       + " (설비보전팀·관리자 전용)")
        return {
            "answer": answer,
            "sources": [{k: d[k] for k in ("doc_id", "version", "title", "section", "access_level")} | {"distance": round(d["distance"], 3)}
                        for d in docs],
            "tools_used": tools_used, "denied": denied, "results": {k: v for k, v in results.items() if k != "search_docs"},
            "parsed": parsed, "mode": AGENT_MODE, "app_filter": APP_FILTER_ENABLED,
            "elapsed_sec": round(time.perf_counter() - start, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        outcome = "error"
        raise HTTPException(503, f"처리 중 오류가 발생했습니다: {type(e).__name__}")
    finally:
        REQUESTS.labels(role, outcome).inc()
        LATENCY.observe(time.perf_counter() - start)
        write_audit(user, question, docs, tools_used, denied, outcome)


def write_audit(user, question, docs, tools, denied, outcome):
    """감사 로그는 답변과 별도 트랜잭션: 답변 처리가 실패해도 기록은 남긴다."""
    try:
        with pool.connection() as conn:
            conn.execute("""INSERT INTO audit_log (user_id, role, question, doc_ids, tools, denied, result)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                         (user["sub"], user["role"], question, sorted({d["doc_id"] for d in docs}), tools, denied, outcome))
    except Exception as e:  # 감사 로그 실패는 앱 로그로라도 남긴다
        print(json.dumps({"event": "audit_write_failed", "error": str(e)}, ensure_ascii=False), flush=True)


# ── 운영 엔드포인트 ──────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        with pool.connection(timeout=3) as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(503, f"DB 연결 불가: {type(e).__name__}")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
