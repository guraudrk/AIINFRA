#!/usr/bin/env python3
"""면접 노트(docs/study/NN-*.md)에서 예상 질문·모범 답변·꼬리 질문을 모아 docs/interview-qa-all.md 를 만든다.
노트를 고치면 다시 실행: python3 scripts/gen_qa.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "docs" / "study"
CHAPTER = {  # 노트 번호 → 개념서 장
    "00": "01-foundations.md", "01": "02-kubernetes.md", "02": "03-llm-serving.md", "03": "04-storage-data.md",
    "04": "05-rag-agent-security.md", "05": "06-network-airgap.md", "06": "07-observability.md",
    "07": "08-backup.md", "08": "09-troubleshooting.md", "09": "10-sizing.md",
}


def section(text, title_prefix):
    m = re.search(rf"^## {re.escape(title_prefix)}.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def parse(note):
    text = note.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    qa = []
    for m in re.finditer(r"^\*\*((?:Q\d+|보너스 Q)\.[^*]+)\*\*.*?\n((?:>.*\n?)+)", section(text, "예상 면접 질문"), re.M):
        answer = " ".join(line.lstrip("> ").strip() for line in m.group(2).splitlines())
        qa.append((m.group(1).strip(), answer))
    tails = re.findall(r"^\d+\.\s+\*\*\"?(.+?)\"?\*\*\s*→", section(text, "꼬리 질문"), re.M)
    return title, qa, tails


def main():
    out = ["# 예상 면접 질문 모음",
           "",
           "> 면접 노트 `docs/study/00~09`의 예상 질문과 모범 답변을 모았습니다(`scripts/gen_qa.py`로 생성).",
           "> 답변은 30~45초 분량의 1인칭 구어체입니다. 막히면 **개념서** 링크로 원리를 다시 확인하세요.",
           "> ✏️ 표시가 있는 답변은 본인 경험으로 직접 채워야 합니다.",
           "",
           "## 사용법",
           "1. 질문만 보고 소리 내어 30초 안에 답해 본다.",
           "2. 모범 답변과 비교해 **수치(측정값)와 \"직접 해 봤다\"는 근거**가 들어갔는지 확인한다.",
           "3. 꼬리 질문 키워드로 한 단계 더 깊은 질문에 답해 본다. 막히면 개념서 해당 장을 읽는다.",
           "",
           "## 목차"]
    notes = sorted(STUDY.glob("[0-9][0-9]-*.md"))
    parsed = [(n, *parse(n)) for n in notes]
    for n, title, qa, _ in parsed:
        anchor = re.sub(r"[^\w가-힣 -]", "", title).strip().lower().replace(" ", "-")
        out.append(f"- [{title}](#{anchor}) — {len(qa)}문항")
    total = 0
    for n, title, qa, tails in parsed:
        num = n.name[:2]
        out += ["", f"## {title}", "",
                f"📘 노트: [{n.name}](study/{n.name}) · 개념서: [{CHAPTER.get(num, '')}](textbook/{CHAPTER.get(num, '')})", ""]
        for q, a in qa:
            total += 1
            out += [f"### {q}", "", f"**답변 (30~45초)** — {a}", ""]
        if tails:
            out += ["**꼬리 질문 키워드**: " + " / ".join(f"\"{t}\"" for t in tails), ""]
    out.insert(4, f"> 총 **{total}문항** (노트 {len(notes)}개)")
    (ROOT / "docs" / "interview-qa-all.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"docs/interview-qa-all.md: {total}문항, 노트 {len(notes)}개")


if __name__ == "__main__":
    main()
