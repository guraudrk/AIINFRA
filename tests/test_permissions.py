"""권한 기반 응답 범위 자동 검증 (표준 라이브러리 unittest만 사용).

같은 질문을 4개 역할로 보내 출처·도구·답변 범위가 역할별로 다른지 확인하고,
DB RLS가 앱과 별개로 행을 막는지도 직접 확인한다.

실행: make test  (scripts/run-tests.sh 가 port-forward와 비밀번호 환경변수를 준비한다)
"""
import json
import os
import subprocess
import unittest
import urllib.request

BASE = os.environ.get("BASE_URL", "http://localhost:18000")
PASSWORD = os.environ["DEMO_PASSWORD"]
NS = os.environ.get("NS", "ai-platform")
QUESTION = "3호기 E-203 대응 방법과 최근 정비 이력 알려줘"
USERS = {"worker": "worker01", "maintenance": "maint01", "quality": "quality01", "admin": "admin01"}
# 품질 보고서(QR-2026-003)에만 있는 표현: 작업자 답변에 나오면 유출
QUALITY_ONLY_MARKERS = ["QR-2026", "860개", "클레임", "11.4mm"]


def call(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)


def ask(role, question=QUESTION):
    token = call("/api/login", {"username": USERS[role], "password": PASSWORD})["token"]
    return call("/api/chat", {"question": question}, token)


def doc_ids(resp):
    return {s["doc_id"] for s in resp["sources"]}


class TestRoleScopes(unittest.TestCase):
    """같은 질문, 역할별로 다른 응답 범위"""

    @classmethod
    def setUpClass(cls):
        cls.r = {role: ask(role) for role in USERS}  # 역할당 1회만 호출 (CPU 추론이 느림)
        for role, resp in cls.r.items():
            print(f"\n[{role}] {resp['elapsed_sec']}s sources={sorted(doc_ids(resp))} "
                  f"tools={resp['tools_used']} denied={resp['denied']}")

    def test_worker_gets_public_only(self):
        levels = {s["access_level"] for s in self.r["worker"]["sources"]}
        self.assertTrue(levels <= {"public"}, f"작업자에게 public 외 문서 노출: {levels}")

    def test_worker_never_receives_quality_report(self):
        resp = self.r["worker"]
        self.assertFalse(any(d.startswith("QR-") for d in doc_ids(resp)))
        text = resp["answer"] + json.dumps(resp["results"], ensure_ascii=False)
        for marker in QUALITY_ONLY_MARKERS:
            self.assertNotIn(marker, text, f"작업자 응답에 품질 보고서 내용 '{marker}' 포함")

    def test_worker_denied_maintenance_history_and_gets_ticket(self):
        resp = self.r["worker"]
        self.assertIn("query_maintenance", resp["denied"])
        self.assertNotIn("query_maintenance", resp["results"])
        self.assertIn("draft_ticket", resp["tools_used"])
        self.assertEqual(resp["results"]["draft_ticket"]["equipment_id"], "PRESS-03")

    def test_maintenance_gets_manual_and_history(self):
        resp = self.r["maintenance"]
        self.assertIn("MAN-PRESS-03", doc_ids(resp))
        self.assertFalse(any(s["access_level"] == "quality" for s in resp["sources"]))
        history = resp["results"]["query_maintenance"]
        self.assertGreaterEqual(len(history), 1)
        self.assertTrue(all(h["alarm"] == "E-203" for h in history))

    def test_maintenance_sees_only_unit3_manual(self):
        """'3호기'를 설비 필터로 걸었으므로 다른 호기 매뉴얼이 섞이면 안 된다 (M3 발견 1)"""
        others = {d for d in doc_ids(self.r["maintenance"]) if d.startswith("MAN-") and d != "MAN-PRESS-03"}
        self.assertEqual(others, set())

    def test_quality_gets_report_not_manual(self):
        resp = self.r["quality"]
        self.assertIn("QR-2026-003", doc_ids(resp))
        self.assertFalse(any(s["access_level"] == "maintenance" for s in resp["sources"]))
        self.assertIn("query_maintenance", resp["denied"])

    def test_admin_sees_everything_relevant(self):
        ids = doc_ids(self.r["admin"])
        self.assertIn("MAN-PRESS-03", ids)
        self.assertIn("QR-2026-003", ids)
        self.assertEqual(self.r["admin"]["denied"], [])


class TestGuardrails(unittest.TestCase):
    def test_unrelated_question_returns_unknown(self):
        """근거가 없으면 LLM을 부르지 않고 '찾을 수 없다'고 답해야 한다 (환각 방지)"""
        resp = ask("admin", "다음 달 회식 장소 추천해줘")
        self.assertEqual(resp["sources"], [])
        self.assertIn("찾을 수 없습니다", resp["answer"])

    def test_requires_login(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            call("/api/chat", {"question": QUESTION})
        self.assertEqual(ctx.exception.code, 401)


class TestDatabaseRLS(unittest.TestCase):
    """앱을 거치지 않고 ax_app 계정으로 직접 조회해도 RLS가 행을 숨기는지 (두 번째 방어선)"""

    def psql_as_app(self, role, sql):
        pw = subprocess.run(["kubectl", "-n", NS, "get", "secret", "postgres-credentials",
                             "-o", "jsonpath={.data.app-password}"], capture_output=True, text=True, check=True).stdout
        pw = subprocess.run(["base64", "-d"], input=pw, capture_output=True, text=True, check=True).stdout
        script = f"BEGIN; SELECT set_config('app.role', '{role}', true) \\gset\n{sql}\nCOMMIT;"
        out = subprocess.run(["kubectl", "-n", NS, "exec", "-i", "postgres-0", "--", "env", f"PGPASSWORD={pw}",
                              "psql", "-h", "localhost", "-U", "ax_app", "-d", "hanbit", "-At"],
                             input=script, capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line and line not in ("BEGIN", "COMMIT")]

    def test_worker_cannot_select_quality_chunks(self):
        self.assertEqual(self.psql_as_app("worker", "SELECT count(*) FROM chunks WHERE access_level <> 'public';"),
                         ["0"])

    def test_worker_cannot_select_maintenance_history(self):
        self.assertEqual(self.psql_as_app("worker", "SELECT count(*) FROM maintenance_history;"), ["0"])

    def test_no_role_means_no_rows(self):
        self.assertEqual(self.psql_as_app("", "SELECT count(*) FROM chunks;"), ["0"])

    def test_quality_can_select_quality_chunks(self):
        count = int(self.psql_as_app("quality", "SELECT count(*) FROM chunks WHERE access_level = 'quality';")[0])
        self.assertGreater(count, 0)


class TestAuditLog(unittest.TestCase):
    def test_worker_denial_is_audited(self):
        rows = subprocess.run(
            ["kubectl", "-n", NS, "exec", "postgres-0", "--", "psql", "-U", "postgres", "-d", "hanbit", "-At", "-c",
             "SELECT count(*) FROM audit_log WHERE user_id = 'worker01' AND 'query_maintenance' = ANY(denied) "
             "AND ts > now() - interval '30 minutes';"],
            capture_output=True, text=True, check=True).stdout.strip()
        self.assertGreaterEqual(int(rows), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
