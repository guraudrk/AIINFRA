#!/usr/bin/env python3
"""프로젝트 소개 페이지 빌드.

  docs/site/page.src.html  (원본: 본문 조각, 이미지 자리표시자)
    → docs/site/page.html  공유 페이지용 (이미지를 data URI로 내장한 조각)
    → docs/index.html      GitHub Pages용 (완전한 HTML 문서, 이미지는 상대 경로)
"""
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "docs/site/page.src.html").read_text(encoding="utf-8")
img = ROOT / "docs/images/m6-grafana-ai-platform.png"

data_uri = "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()
(ROOT / "docs/site/page.html").write_text(src.replace("__GRAFANA_IMG__", data_uri), encoding="utf-8")

full = ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        + src.replace("__GRAFANA_IMG__", "images/m6-grafana-ai-platform.png")
             .replace("<div class=\"wrap\">", "</head>\n<body style=\"margin:0\">\n<div class=\"wrap\">", 1)
        + "\n</body>\n</html>\n")
(ROOT / "docs/index.html").write_text(full, encoding="utf-8")
print("docs/site/page.html, docs/index.html 생성")
