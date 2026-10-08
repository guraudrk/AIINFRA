#!/usr/bin/env bash
# 총정리 PDF 다시 만들기 (WSL에서 실행, Windows Edge로 인쇄)
#   ./scripts/make-pdf.sh                 기본: OneDrive 면접 폴더에 저장
#   ./scripts/make-pdf.sh /mnt/c/경로/파일.pdf
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-/mnt/c/Users/user/OneDrive/바탕 화면/이장한/취업/2026 하반기/면접/에티버스이피에이_AI시스템엔지니어_1013/05_AX_Platform_Lab_총정리.pdf}"
EDGE="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
HTML=/mnt/c/Users/user/AppData/Local/Temp/ax-total.html

python3 scripts/gen_qa.py                      # 노트를 고쳤다면 질문 모음도 갱신
python3 scripts/build-pdf.py "$HTML"
"$EDGE" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=25000 \
  --print-to-pdf="$(wslpath -w "$OUT")" "file:///$(wslpath -m "$HTML")" 2>/dev/null | tail -1
echo "PDF: $OUT"
