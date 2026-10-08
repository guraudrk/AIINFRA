#!/usr/bin/env python3
"""총정리 PDF용 단일 HTML 생성: 문서들을 부(part) 단위로 묶고, Markdown 렌더러와 다이어그램 라이브러리를 내장한다.
PDF 인쇄는 Windows Edge(headless)로 한다:
  python3 scripts/build-pdf.py <출력 HTML 경로>
  msedge --headless=new --no-pdf-header-footer --virtual-time-budget=30000 --print-to-pdf=<pdf> <html>
"""
import base64
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs"
CACHE = Path("/tmp/ax-pdf-libs")
LIBS = {
    "marked.min.js": "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js",
    "mermaid.min.js": "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js",
}

PARTS = [
    ("0부. 면접 당일 요약", "면접 직전에 이 부만 읽어도 된다", [D / "interview-cheatsheet.md"]),
    ("1부. 프로젝트 개요", "무엇을, 왜, 어떻게 만들었고 무엇을 측정했나", [D / "portfolio-onepager.md", ROOT / "README.md"]),
    ("2부. 예상 면접 질문 54개", "질문 → 30~45초 답변 → 꼬리 질문 키워드", [D / "interview-qa-all.md"]),
    ("3부. 개념서", "개념마다 정의 · 왜 필요한가 · 동작 원리 · 이 프로젝트 · 흔한 오해 · 실무 · 면접 한 줄",
     sorted((D / "textbook").glob("[0-9][0-9]-*.md"))),
    ("4부. 모듈별 면접 노트", "M0~M9에서 실제로 한 일, 측정값, 겪은 문제, 용어 풀이",
     sorted((D / "study").glob("[0-9][0-9]-*.md"))),
    ("5부. 보고서 · 제안서 · 절차서 · 런북", "고객에게 내는 형식의 산출물",
     [D / "proposal-sample.md", D / "incident-report-sample.md", D / "restore-drill-report.md", D / "airgap-install.md",
      ROOT / "runbooks/alerts.md", *sorted((ROOT / "runbooks").glob("0*.md"))]),
    ("부록. 개발 환경", "M0 점검 결과", [D / "00-environment.md"]),
]


def lib(name):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / name
    if not f.exists():
        f.write_bytes(urllib.request.urlopen(LIBS[name], timeout=60).read())
    return f.read_text(encoding="utf-8")


def one_liners():
    out = []
    for f in sorted((D / "textbook").glob("[0-9][0-9]-*.md")):
        text = f.read_text(encoding="utf-8")
        chapter = text.splitlines()[0].lstrip("# ").strip()
        items = []
        for sec in re.split(r"^## ", text, flags=re.M)[1:]:
            title = sec.splitlines()[0].strip()
            m = re.search(r"\*\*면접 한 줄\*\*:\s*(.+)", sec)
            if m:
                items.append(f"- **{title}** — {m.group(1).strip()}")
        if items:
            out.append(f"\n**{chapter}**\n\n" + "\n".join(items))
    return "\n".join(out)


def prepare(md, src):
    # 이미지 → data URI (PDF 안에 내장)
    def img(m):
        p = (src.parent / m.group(2)).resolve()
        if p.exists():
            return f"![{m.group(1)}](data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()})"
        return m.group(1)
    md = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", img, md)
    # 문서 간 상대 링크 → 글자만 (PDF에서는 동작하지 않으므로), 외부 링크는 유지
    md = re.sub(r"(?<!!)\[([^\]]+)\]\((?!https?://|data:|#)[^)]+\)", r"\1", md)
    # 제목 단계를 한 칸 내림 (# 문서 제목 → ##), 코드 블록 안은 제외
    lines, fence = [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and re.match(r"^#{1,5} ", line):
            line = "#" + line
        lines.append(line)
    return "\n".join(lines)


def main():
    out_path = Path(sys.argv[1])
    docs, toc = [], []
    for pi, (part, sub, files) in enumerate(PARTS):
        pid = f"part{pi}"
        toc.append(f'<li class="toc-part"><a href="#{pid}">{html.escape(part)}</a> <span>{html.escape(sub)}</span><ol>')
        docs.append({"type": "part", "id": pid, "title": part, "sub": sub})
        for fi, f in enumerate(files):
            md = f.read_text(encoding="utf-8")
            if f.name == "interview-cheatsheet.md":
                md = md.replace("(개념서 각 절의 \"면접 한 줄\" — 자동 수집)", one_liners())
            title = md.splitlines()[0].lstrip("# ").strip()
            did = f"{pid}-{fi}"
            toc.append(f'<li><a href="#{did}">{html.escape(title)}</a></li>')
            docs.append({"type": "doc", "id": did, "md": prepare(md, f)})
        toc.append("</ol></li>")

    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AX Platform Lab 총정리</title>
<style>
@page {{ size: A4; margin: 16mm 15mm 18mm;
  @bottom-center {{ content: counter(page) " / " counter(pages); font: 9pt "Malgun Gothic"; color: #6b7a83; }}
  @top-right {{ content: "AX Platform Lab 총정리 · 이장한"; font: 8pt "Malgun Gothic"; color: #9aa7ae; }} }}
@page :first {{ @bottom-center {{ content: none; }} @top-right {{ content: none; }} }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Malgun Gothic", sans-serif; font-size: 10pt; line-height: 1.6; color: #17232b; margin: 0; }}
.cover {{ height: 255mm; display: flex; flex-direction: column; justify-content: center; gap: 14px; border-left: 6px solid #0b6e8a; padding-left: 18mm; }}
.cover .eyebrow {{ font-size: 10pt; letter-spacing: .12em; color: #5a6b75; }}
.cover h1 {{ font-size: 30pt; margin: 0; line-height: 1.2; }}
.cover h1 span {{ color: #0b6e8a; }}
.cover p {{ font-size: 11.5pt; max-width: 150mm; margin: 0; color: #33444d; }}
.cover .meta {{ font-size: 10pt; color: #5a6b75; margin-top: 18px; }}
.toc {{ page-break-before: always; }}
.toc h1 {{ font-size: 18pt; border-bottom: 3px solid #17232b; padding-bottom: 6px; }}
.toc ol {{ padding-left: 18px; }} .toc li {{ margin: 3px 0; }}
.toc > ol {{ list-style: none; padding-left: 0; }}
.toc .toc-part {{ margin-top: 10px; font-weight: 700; }} .toc .toc-part span {{ font-weight: 400; color: #5a6b75; font-size: 9pt; }}
.toc .toc-part ol li {{ font-weight: 400; }}
.toc a {{ color: #17232b; text-decoration: none; }}
.howto {{ background: #eef4f6; border: 1px solid #cfdfe5; padding: 10px 14px; margin-top: 14px; font-size: 9.5pt; }}
section.part {{ page-break-before: always; height: 250mm; display: flex; flex-direction: column; justify-content: center; border-left: 6px solid #c98a00; padding-left: 16mm; }}
section.part h1 {{ font-size: 26pt; margin: 0; }} section.part p {{ font-size: 12pt; color: #5a6b75; }}
section.doc {{ page-break-before: always; }}
h2 {{ font-size: 17pt; border-bottom: 2px solid #0b6e8a; padding-bottom: 4px; margin: 0 0 10px; }}
h3 {{ font-size: 13pt; margin: 18px 0 6px; color: #0b4f63; break-after: avoid; }}
h4 {{ font-size: 11pt; margin: 14px 0 4px; break-after: avoid; }}
h5, h6 {{ font-size: 10.5pt; margin: 10px 0 4px; break-after: avoid; }}
p {{ margin: 5px 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; break-inside: auto; }}
th, td {{ border: 1px solid #c9d4d9; padding: 4px 6px; vertical-align: top; text-align: left; }}
th {{ background: #eef2f4; }} tr {{ break-inside: avoid; }}
code {{ font-family: Consolas, "Malgun Gothic", monospace; font-size: 8.8pt; background: #f1f4f6; padding: 0 3px; }}
pre {{ background: #f4f6f7; border: 1px solid #dde4e8; padding: 8px 10px; white-space: pre-wrap; word-break: break-all; font-size: 8.5pt; break-inside: avoid; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ margin: 8px 0; padding: 6px 12px; border-left: 4px solid #0b6e8a; background: #f3f8fa; color: #24343d; }}
img {{ max-width: 100%; border: 1px solid #c9d4d9; }}
.mermaid {{ text-align: center; margin: 10px 0; break-inside: avoid; }}
a {{ color: #0b6e8a; }}
ul, ol {{ padding-left: 20px; }} li {{ margin: 2px 0; }}
</style></head><body>
<div class="cover">
  <div class="eyebrow">PORTFOLIO PROJECT · 면접 총정리</div>
  <h1>AX Platform Lab<br><span>권한 기반 사내 AI 플랫폼</span><br>구축·운영 총정리</h1>
  <p>가상 제조사 한빛정밀의 sLLM + RAG + AI 에이전트를 GPU 쿠버네티스에 구축하고, 보안·폐쇄망·모니터링·백업·장애 대응·사이징까지 운영 업무를 재현한 프로젝트의 모든 결과와 개념, 예상 질문을 한 권에 담았습니다.</p>
  <div class="meta">이장한 · 에티버스이피에이 AI 시스템 엔지니어 실무면접 준비 · {date.today()}<br>
  GitHub github.com/guraudrk/AIINFRA · 소개 페이지 guraudrk.github.io/AIINFRA</div>
</div>
<div class="toc"><h1>목차</h1>
<div class="howto"><b>이 문서 사용법</b> — 면접 직전에는 <b>0부</b>만, 처음 읽을 때는 <b>1부 → 2부</b> 순서로, 답이 막히는 질문은 <b>3부 개념서</b>의 해당 장을, 수치와 실제 과정이 궁금하면 <b>4부 노트</b>를 봅니다. 5부는 고객에게 내는 형식의 산출물입니다.</div>
<ol>{''.join(toc)}</ol></div>
<div id="content"></div>
<script>{lib("marked.min.js")}</script>
<script>{lib("mermaid.min.js")}</script>
<script>
const DOCS = {json.dumps(docs, ensure_ascii=False)};
const root = document.getElementById("content");
for (const d of DOCS) {{
  const s = document.createElement("section");
  s.id = d.id;
  if (d.type === "part") {{ s.className = "part"; s.innerHTML = `<h1>${{d.title}}</h1><p>${{d.sub}}</p>`; }}
  else {{ s.className = "doc"; s.innerHTML = marked.parse(d.md); }}
  root.appendChild(s);
}}
document.querySelectorAll("pre code.language-mermaid").forEach(c => {{
  const div = document.createElement("div"); div.className = "mermaid"; div.textContent = c.textContent;
  c.parentElement.replaceWith(div);
}});
mermaid.initialize({{ startOnLoad: false, theme: "neutral", flowchart: {{ htmlLabels: true }} }});
mermaid.run().then(() => {{ document.title = "READY"; }});
</script></body></html>"""
    out_path.write_text(page, encoding="utf-8")
    print(f"{out_path} ({len(page) // 1024} KB), 문서 {sum(1 for d in docs if d['type'] == 'doc')}개")


if __name__ == "__main__":
    main()
