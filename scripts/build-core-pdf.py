#!/usr/bin/env python3
"""핵심 요약본(docs/core-summary.md) → 단일 HTML (PDF 인쇄용). build-pdf.py의 Markdown 처리·라이브러리를 재사용한다.
  python3 scripts/build-core-pdf.py <출력 HTML>
"""
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("buildpdf", ROOT / "scripts" / "build-pdf.py")
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

src = ROOT / "docs" / "core-summary.md"
md = src.read_text(encoding="utf-8")
chapters = re.findall(r"^## (.+)$", md, re.M)
body = bp.prepare("\n".join(md.splitlines()[1:]), src)   # 첫 줄 제목은 표지로 대체
toc = "".join(f'<li><a href="#c{i}">{c}</a></li>' for i, c in enumerate(chapters))

page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AX Platform Lab 핵심 요약본</title>
<style>
@page {{ size: A4; margin: 13mm 13mm 15mm;
  @bottom-center {{ content: counter(page) " / " counter(pages); font: 8.5pt "Malgun Gothic"; color: #6b7a83; }}
  @top-right {{ content: "핵심 요약본 · 하루 2회독"; font: 7.5pt "Malgun Gothic"; color: #9aa7ae; }} }}
@page :first {{ @bottom-center {{ content: none; }} @top-right {{ content: none; }} }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Malgun Gothic", sans-serif; font-size: 9.4pt; line-height: 1.55; color: #17232b; margin: 0; }}
.cover {{ height: 262mm; display: flex; flex-direction: column; justify-content: center; gap: 12px; border-left: 6px solid #c98a00; padding-left: 16mm; }}
.cover .eyebrow {{ font-size: 9.5pt; letter-spacing: .12em; color: #5a6b75; }}
.cover h1 {{ font-size: 28pt; margin: 0; line-height: 1.22; }} .cover h1 span {{ color: #b07800; }}
.cover p {{ font-size: 11pt; max-width: 150mm; margin: 0; color: #33444d; }}
.cover .plan {{ margin-top: 14px; border: 1px solid #e3d3a8; background: #fbf6e9; padding: 10px 14px; max-width: 150mm; font-size: 10pt; }}
.cover .toc {{ margin-top: 10px; font-size: 10pt; }} .cover .toc a {{ color: #17232b; text-decoration: none; }}
.cover .toc ol {{ margin: 4px 0; padding-left: 18px; }}
.cover .meta {{ font-size: 9pt; color: #5a6b75; margin-top: 10px; }}
h3 {{ page-break-before: always; font-size: 15pt; border-bottom: 2px solid #b07800; padding-bottom: 3px; margin: 0 0 8px; }}
h3.first {{ page-break-before: always; }}
h4 {{ font-size: 11pt; margin: 12px 0 4px; color: #0b4f63; break-after: avoid; }}
h5 {{ font-size: 10pt; margin: 10px 0 3px; break-after: avoid; }}
p {{ margin: 4px 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 8.5pt; }}
th, td {{ border: 1px solid #cdd6da; padding: 3px 5px; vertical-align: top; text-align: left; }}
th {{ background: #f3efe3; }} tr {{ break-inside: avoid; }}
strong {{ color: #0b3f50; }}
code {{ font-family: Consolas, "Malgun Gothic", monospace; font-size: 8.3pt; background: #f1f4f6; padding: 0 3px; }}
pre {{ background: #f4f6f7; border: 1px solid #dde4e8; padding: 6px 8px; white-space: pre-wrap; font-size: 8pt; break-inside: avoid; }}
pre code {{ background: none; }}
blockquote {{ margin: 6px 0; padding: 6px 10px; border-left: 4px solid #b07800; background: #fbf6e9; }}
ul, ol {{ padding-left: 18px; margin: 4px 0; }} li {{ margin: 1.5px 0; }}
.mermaid {{ text-align: center; margin: 6px 0; break-inside: avoid; }} .mermaid svg {{ max-height: 70mm; }}
hr {{ display: none; }}
</style></head><body>
<div class="cover">
  <div class="eyebrow">AX PLATFORM LAB · 면접 벼락치기</div>
  <h1>핵심만 모았다<br><span>하루 2회독 핵심 요약본</span></h1>
  <p>권한 기반 사내 AI 플랫폼 프로젝트의 수치, 용어, 원리, 사례, 예상 질문을 하루 안에 두 번 읽을 분량으로 압축했습니다.</p>
  <div class="plan"><b>1회독 (2~3시간)</b> 1~6장 정독, 굵은 수치와 "면접 한 줄"에 표시, 5장은 소리 내어 답하기<br>
  <b>2회독 (1시간)</b> 굵은 글씨·표만 훑기 → 7장 퀴즈 30문항 → 틀린 것만 다시<br>
  <b>면접 직전 (15분)</b> 1장 수치표 · 4장 사례 5개 · 6장 자기소개</div>
  <div class="toc"><b>목차</b><ul style="list-style:none;padding-left:0">{toc}</ul></div>
  <div class="meta">이장한 · 에티버스이피에이 AI 시스템 엔지니어 실무면접 · {date.today()} · 전체 상세본: 05_AX_Platform_Lab_총정리.pdf</div>
</div>
<div id="content"></div>
<script>{bp.lib("marked.min.js")}</script>
<script>{bp.lib("mermaid.min.js")}</script>
<script>
const root = document.getElementById("content");
root.innerHTML = marked.parse({json.dumps(body, ensure_ascii=False)});
root.querySelectorAll("h3").forEach((h, i) => {{ h.id = "c" + i; }});
document.querySelectorAll("pre code.language-mermaid").forEach(c => {{
  const d = document.createElement("div"); d.className = "mermaid"; d.textContent = c.textContent; c.parentElement.replaceWith(d);
}});
mermaid.initialize({{ startOnLoad: false, theme: "neutral" }});
mermaid.run().then(() => {{ document.title = "READY"; }});
</script></body></html>"""
out = Path(sys.argv[1])
out.write_text(page, encoding="utf-8")
print(f"{out} ({len(page) // 1024} KB), 장 {len(chapters)}개")
