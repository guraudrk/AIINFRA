#!/usr/bin/env python3
"""가상 제조사 "한빛정밀" 데이터 생성기 (모든 내용은 가상이다).

출력
  data/docs/*.md   설비 매뉴얼 10, 사내 규정 3, 품질 불량 보고서 5 (앞부분 YAML 메타데이터)
  data/csv/*.csv   equipment, alarm_codes, parts, stock, maintenance_history,
                   alarm_parts, alarm_documents (온톨로지 관계)

seed를 고정해서 몇 번을 실행해도 같은 결과가 나온다.
  python3 scripts/gen_data.py
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
ROOT = Path(__file__).resolve().parent.parent / "data"
DOCS, CSVS = ROOT / "docs", ROOT / "csv"
TODAY = date(2026, 10, 7)

# ── 설비 ────────────────────────────────────────────────────
EQUIPMENT = (
    [{"equipment_id": f"PRESS-0{i}", "name": f"프레스 {i}호기", "type": "press", "line": "A라인",
      "model": "HBP-800" if i != 3 else "HBP-800H", "install_year": 2016 + i} for i in range(1, 6)]
    + [{"equipment_id": f"CNC-0{i}", "name": f"CNC {i}호기", "type": "cnc", "line": "B라인",
        "model": "HBC-5X", "install_year": 2018 + (i % 3)} for i in range(1, 6)]
)

# ── 부품 ────────────────────────────────────────────────────
PARTS = [
    ("P-ELC-001", "메인 모터 열동 계전기", "전기"), ("P-ELC-002", "비상정지 스위치 접점 블록", "전기"),
    ("P-ELC-003", "PLC 통신 케이블(이더넷)", "전기"), ("P-ELC-004", "서보 드라이브 냉각팬", "전기"),
    ("P-HYD-001", "유압 펌프 씰 키트", "유압"), ("P-HYD-002", "유압 압력 센서", "유압"),
    ("P-HYD-003", "유압 필터 엘리먼트", "유압"), ("P-HYD-004", "릴리프 밸브", "유압"),
    ("P-HYD-005", "유압유 냉각기 팬", "유압"), ("P-HYD-006", "유압유 ISO VG46 (20L)", "유압"),
    ("P-PNE-001", "공압 레귤레이터", "공압"), ("P-PNE-002", "공압 솔레노이드 밸브", "공압"),
    ("P-LUB-001", "자동 윤활 펌프", "윤활"), ("P-LUB-002", "절삭유 펌프", "윤활"),
    ("P-LUB-003", "절삭유 필터", "윤활"), ("P-MEC-001", "슬라이드 조정 모터 브레이크", "기계"),
    ("P-MEC-002", "엔드밀 Ø10 초경", "공구"), ("P-SAF-001", "안전 광커튼 수광부", "안전"),
    ("P-SAF-002", "도어 인터록 스위치", "안전"),
]

# ── 경보 코드: E-1xx 전기·제어 / E-2xx 유압·공압·윤활 / E-3xx 기계·안전 ──
ALARMS = {
    "press": [
        ("E-101", "메인 모터 과부하", "전기", "high",
         ["연속 고속 운전으로 모터 과열", "클러치 미끄럼으로 부하 증가", "열동 계전기 설정값 불량"],
         ["운전 정지 후 모터 표면 온도를 비접촉 온도계로 확인한다(80℃ 이하까지 냉각)",
          "열동 계전기 트립 여부와 설정값(정격 전류 105%)을 확인한다",
          "클러치 공기압과 라이닝 마모를 점검한다", "재기동 후 무부하 운전 10분으로 전류값을 기록한다"],
         ["P-ELC-001"], "모터 단자함은 반드시 메인 차단기 OFF와 잠금·표지(LOTO) 후 개방한다."),
        ("E-102", "비상정지 회로 작동", "전기", "critical",
         ["작업자가 비상정지 버튼을 누름", "비상정지 스위치 접점 불량", "안전 릴레이 배선 단선"],
         ["비상정지가 눌린 위치를 확인하고 현장 안전을 확인한다",
          "버튼 복귀 후에도 경보가 남으면 접점 블록 도통을 측정한다",
          "안전 릴레이 입력 LED 상태를 확인한다"],
         ["P-ELC-002"], "원인을 확인하기 전에 비상정지를 해제하거나 우회 배선하지 않는다."),
        ("E-115", "PLC 통신 이상", "전기", "medium",
         ["이더넷 케이블 접촉 불량", "스위칭 허브 전원 이상", "PLC IP 충돌"],
         ["PLC 통신 포트 LED(Link/Act)를 확인한다", "케이블을 재체결하고 통신 재시도한다",
          "HMI 진단 화면에서 IP 충돌 이력을 확인한다"],
         ["P-ELC-003"], "운전 중 케이블 분리는 금형 동작 이상을 유발할 수 있으니 정지 상태에서 작업한다."),
        ("E-201", "유압유 온도 상승", "유압", "medium",
         ["유압유 냉각기 팬 정지", "유압유 부족", "릴리프 밸브 상시 개방으로 발열"],
         ["유압유 온도계를 확인한다(정상 35~55℃, 65℃ 이상 시 정지)", "냉각기 팬 회전 여부를 확인한다",
          "유면계로 유량을 확인하고 부족 시 ISO VG46을 보충한다"],
         ["P-HYD-005", "P-HYD-006"], "고온 유압유에 의한 화상에 주의한다. 배관 접촉 금지."),
        ("E-203", "유압 압력 저하", "유압", "high",
         ["유압 필터 막힘으로 흡입 불량", "유압 펌프 씰 마모로 내부 누유", "압력 센서 고장(오검출)", "릴리프 밸브 설정 이탈"],
         ["운전을 정지하고 메인 압력 게이지 값을 기록한다",
          "유압 필터 차압 표시기를 확인하고 적색이면 필터 엘리먼트를 교체한다",
          "펌프 주변 누유 흔적을 점검하고 누유 시 씰 키트를 교체한다",
          "게이지 값은 정상인데 경보가 뜨면 압력 센서 출력(4~20mA)을 측정한다",
          "릴리프 밸브 설정 압력을 확인하고 기준값으로 재조정한다",
          "조치 후 무부하 운전 15분 동안 압력 안정 여부를 확인한다"],
         ["P-HYD-003", "P-HYD-001", "P-HYD-002", "P-HYD-004"],
         "유압 라인은 잔압 제거(어큐뮬레이터 방출) 후 분해한다. 고압 유압유 분사로 인한 부상 위험."),
        ("E-210", "공압 압력 저하(클러치·브레이크)", "공압", "high",
         ["공장 공압 라인 압력 부족", "공압 레귤레이터 고장", "솔레노이드 밸브 누설"],
         ["공압 게이지를 확인한다(기준 0.5MPa)", "레귤레이터 설정과 드레인 상태를 점검한다",
          "솔레노이드 밸브 배기음으로 누설 여부를 확인한다"],
         ["P-PNE-001", "P-PNE-002"], "공압 저하 시 브레이크 성능이 떨어지므로 슬라이드를 하사점에 두고 점검한다."),
        ("E-301", "금형 높이 이상", "기계", "medium",
         ["슬라이드 조정 모터 브레이크 마모", "금형 교체 후 다이하이트 미설정"],
         ["다이하이트 표시값과 금형 사양서를 비교한다", "슬라이드 조정 후 인칭 운전으로 하사점을 확인한다"],
         ["P-MEC-001"], "인칭 운전 중에는 금형 영역에 손을 넣지 않는다."),
        ("E-305", "안전 광커튼 차단", "안전", "critical",
         ["작업자 신체가 위험 영역에 진입", "광커튼 오염·정렬 불량", "수광부 고장"],
         ["위험 영역에 사람이나 물체가 없는지 확인한다", "투·수광부 렌즈를 청소하고 정렬 표시등을 확인한다",
          "지속 시 수광부를 교체한다"],
         ["P-SAF-001"], "광커튼을 비활성화한 상태로 생산하는 것은 금지되어 있다(안전 규정 3조)."),
    ],
    "cnc": [
        ("E-101", "스핀들 모터 과부하", "전기", "high",
         ["과도한 절삭 조건", "공구 마모로 절삭 저항 증가", "스핀들 베어링 손상"],
         ["가공 프로그램의 회전수·이송 속도를 확인한다", "공구 마모 상태를 확인한다",
          "무부하 회전 시 이음·진동을 점검한다"],
         ["P-MEC-002"], "스핀들 정지 확인 후 공구에 접근한다."),
        ("E-104", "서보 드라이브 알람", "전기", "high",
         ["서보 드라이브 과열", "엔코더 케이블 노이즈", "축 기계적 구속"],
         ["드라이브 표시 코드를 기록한다", "드라이브 냉각팬 동작을 확인한다", "축을 수동으로 이동해 걸림을 확인한다"],
         ["P-ELC-004"], "드라이브 내부 콘덴서 잔류 전압 방전(5분) 후 작업한다."),
        ("E-120", "NC 통신 이상", "전기", "medium",
         ["DNC 케이블 불량", "네트워크 설정 오류"],
         ["NC 네트워크 설정을 확인한다", "케이블 재체결 후 프로그램 재전송한다"],
         ["P-ELC-003"], "프로그램 전송 중 가공 시작 금지."),
        ("E-202", "절삭유 압력 저하", "윤활", "medium",
         ["절삭유 필터 막힘", "절삭유 펌프 고장", "절삭유 부족"],
         ["절삭유 탱크 유량을 확인한다", "필터를 청소·교체한다", "펌프 토출 압력을 확인한다"],
         ["P-LUB-003", "P-LUB-002"], "절삭유 접촉 시 피부 보호구를 착용한다."),
        ("E-207", "윤활유 부족", "윤활", "low",
         ["자동 윤활 탱크 유량 부족", "윤활 펌프 고장"],
         ["윤활 탱크에 지정 윤활유를 보충한다", "수동 윤활 버튼으로 토출을 확인한다"],
         ["P-LUB-001"], "지정 외 윤활유 혼용 금지."),
        ("E-211", "공압 압력 저하(공구 클램프)", "공압", "high",
         ["공압 라인 압력 부족", "레귤레이터 고장"],
         ["공압 게이지를 확인한다(기준 0.6MPa)", "공구 클램프 동작을 수동으로 확인한다"],
         ["P-PNE-001"], "클램프 압력 부족 상태로 가공하면 공구가 이탈할 수 있다."),
        ("E-302", "공구 마모 한계 초과", "기계", "low",
         ["공구 수명 카운터 도달"],
         ["공구를 교체하고 공구 길이를 재측정한다", "수명 카운터를 초기화한다"],
         ["P-MEC-002"], "공구 교체 시 절삭날 보호 장갑 착용."),
        ("E-308", "도어 인터록 열림", "안전", "critical",
         ["가공 중 도어 개방", "인터록 스위치 고장"],
         ["도어 닫힘 상태를 확인한다", "인터록 스위치 동작을 점검하고 불량 시 교체한다"],
         ["P-SAF-002"], "인터록 우회(점퍼) 운전 금지."),
    ],
}

UNIT_NOTES = {
    "PRESS-03": "2024년 유압 펌프를 고압형(HP-450)으로 교체했다. 메인 유압 기준 압력은 21MPa(다른 호기 18MPa)이고, "
                "압력 센서는 0~35MPa 레인지를 쓴다. 2026년 들어 E-203 발생 빈도가 높아 필터 교체 주기를 500시간에서 300시간으로 단축했다.",
}


def front_matter(meta):
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n\n"


def write_manuals():
    for eq in EQUIPMENT:
        alarms = ALARMS[eq["type"]]
        doc_id = f"MAN-{eq['equipment_id']}"
        version = "3.1" if eq["equipment_id"] == "PRESS-03" else random.choice(["2.0", "2.1", "2.3"])
        base_p = "21MPa" if eq["equipment_id"] == "PRESS-03" else "18MPa"
        lines = [front_matter({"doc_id": doc_id, "title": f"{eq['name']} 설비 매뉴얼", "dept": "설비보전팀",
                               "access_level": "maintenance", "version": version, "equipment_id": eq["equipment_id"]}),
                 f"# {eq['name']} 설비 매뉴얼 (v{version})\n",
                 "## 1. 설비 개요\n",
                 f"- 설비 ID: {eq['equipment_id']} / 모델: {eq['model']} / 위치: {eq['line']} / 설치: {eq['install_year']}년",
                 f"- 기준값: 메인 유압 {base_p}, 공압 0.5MPa, 유압유 온도 35~55℃" if eq["type"] == "press"
                 else "- 기준값: 스핀들 최대 12,000rpm, 공압 0.6MPa, 절삭유 압력 0.3MPa",
                 ""]
        if eq["equipment_id"] in UNIT_NOTES:
            lines += ["## 2. 호기별 특이사항\n", UNIT_NOTES[eq["equipment_id"]], ""]
        lines.append("## 3. 경보 코드별 원인과 조치\n")
        for code, title, cat, sev, causes, actions, parts, safety in alarms:
            part_names = ", ".join(f"{p}({dict((x[0], x[1]) for x in PARTS)[p]})" for p in parts)
            lines += [f"### {code} {title}\n",
                      f"- 분류: {cat} / 심각도: {sev}",
                      "- 예상 원인:", *[f"  {i}. {c}" for i, c in enumerate(causes, 1)],
                      "- 조치 순서:", *[f"  {i}. {a}" for i, a in enumerate(actions, 1)],
                      f"- 필요 부품: {part_names}",
                      f"- 안전 주의: {safety}", ""]
        lines += ["## 4. 정기 점검\n",
                  "- 일일: 유압·공압 게이지, 누유, 이음 확인 (작업 시작 전)" if eq["type"] == "press"
                  else "- 일일: 절삭유·윤활유 유량, 칩 제거, 도어 인터록 확인",
                  "- 월간: 필터 차압, 안전장치 기능 시험, 전기 단자 조임",
                  "- 연간: 유압유 교환, 정밀도 측정, 안전 인증 점검", ""]
        (DOCS / f"{doc_id}.md").write_text("\n".join(lines), encoding="utf-8")


REGULATIONS = [
    ("REG-SAFETY", "안전 관리 규정", "안전환경팀", "public", "4.0", """
# 안전 관리 규정 (v4.0)

## 제1조 목적
이 규정은 한빛정밀 생산 현장에서 작업자와 설비의 안전을 확보하기 위한 기준을 정한다.

## 제2조 설비 경보 발생 시 작업자 행동 요령
1. 경보가 울리면 즉시 설비를 정지(사이클 스톱)하고, 위험하면 비상정지 버튼을 누른다.
2. 경보 코드와 발생 시각을 HMI 화면에서 확인해 기록한다.
3. 작업자는 유압·전기 계통을 직접 분해하거나 조정하지 않는다. 덮개를 열지 않는다.
4. 정비 요청 절차(REG-MAINT-REQ)에 따라 설비보전팀에 정비를 요청한다.
5. 유압유 누유가 보이면 주변을 통제하고 미끄럼 방지 흡착포를 깐다.
6. 설비보전팀의 확인 전에는 재가동하지 않는다.

## 제3조 안전장치
광커튼, 도어 인터록, 비상정지 회로를 비활성화하거나 우회한 상태로 생산하는 것을 금지한다.
위반 시 인사 규정에 따라 조치한다.

## 제4조 잠금·표지(LOTO)
전기·유압·공압 에너지를 다루는 정비 작업은 에너지원 차단, 잠금장치 체결, 표지 부착 후 시작한다.
잔압(유압 어큐뮬레이터, 공압 탱크) 방출을 확인한다.

## 제5조 보호구
프레스·CNC 작업 시 안전화, 보안경, 장갑을 착용한다. 유압 정비 시 내유성 장갑을 착용한다.
"""),
    ("REG-MAINT-REQ", "정비 요청 및 처리 절차", "설비보전팀", "public", "2.2", """
# 정비 요청 및 처리 절차 (v2.2)

## 1. 적용 범위
생산 설비의 고장·경보·이상 징후에 대한 정비 요청부터 처리 완료까지의 절차를 정한다.

## 2. 요청 방법
- 사내 AI 플랫폼의 정비 요청(티켓) 또는 설비보전팀 내선 3200으로 요청한다.
- 필수 항목: 설비 ID, 경보 코드, 발생 시각, 증상, 요청자, 생산 영향(정지/감속/정상).

## 3. 처리 단계
1. 접수: 설비보전팀 당직자가 15분 이내 접수하고 우선순위를 정한다(critical 30분, high 2시간, medium 당일, low 주간).
2. 진단: 담당 정비원이 현장 확인 후 원인을 기록한다.
3. 조치: 부품이 필요하면 재고를 확인하고, 없으면 구매 요청한다.
4. 확인: 요청자와 함께 재가동을 확인한다.
5. 기록: 정비 이력 시스템에 원인, 조치, 사용 부품, 정지 시간을 남긴다.

## 4. 반복 고장 관리
같은 설비에서 같은 경보가 30일 내 3회 이상 발생하면 근본 원인 분석(RCA)을 실시하고 예방 정비 계획에 반영한다.
"""),
    ("REG-SECURITY", "정보보안 규정", "정보보안팀", "public", "1.3", """
# 정보보안 규정 (v1.3)

## 1. 정보 등급
- 공개(public): 전 직원 열람 가능 (안전 규정, 절차서)
- 정비(maintenance): 설비보전팀 및 관리자 (설비 매뉴얼, 정비 이력)
- 품질(quality): 품질팀 및 관리자 (불량 보고서, 고객 클레임)
- 관리(admin): 관리자 전용

## 2. 접근 권한
- 권한은 소속 부서와 직무 기준으로 부여한다. 권한 요청은 요청-검토-승인-반영-이력 관리 절차를 따른다.
- 퇴사·전보 시 당일 권한을 회수한다.

## 3. AI 플랫폼 사용
- 사내 AI 플랫폼은 사용자 권한 범위의 문서만 검색·답변에 사용한다.
- 모든 질의와 사용된 문서는 감사 로그에 기록되며 1년간 보관한다.
- 외부 생성형 AI 서비스에 사내 문서·도면·고객 정보를 입력하는 것을 금지한다.
"""),
]

QUALITY_REPORTS = [
    ("QR-2026-001", "CNC 2호기 치수 불량(내경 공차 초과)", "CNC-02", "E-302", "2026-03-14",
     "내경 Ø32 H7 공차 상한 초과 품목 48개 발생.", "공구 마모 한계 초과 상태에서 가공 지속(E-302 경보 무시 후 재시작).",
     "전수 선별 후 48개 폐기. 공구 수명 카운터 강제 정지 설정. 작업자 재교육."),
    ("QR-2026-002", "프레스 1호기 버(burr) 과다", "PRESS-01", "E-301", "2026-04-22",
     "브래킷 외곽 버 높이 0.3mm 초과(기준 0.1mm) 1,200개.", "금형 교체 후 다이하이트 미설정(E-301)으로 클리어런스 과다.",
     "재작업 후 출하. 금형 교체 체크리스트에 다이하이트 확인 항목 추가."),
    ("QR-2026-003", "프레스 3호기 성형 깊이 부족", "PRESS-03", "E-203", "2026-09-18",
     "도어 힌지 보강판 성형 깊이 부족(기준 12.0±0.2mm, 측정 11.4mm) 860개. 고객사 입고 검사에서 발견되어 클레임 접수.",
     "유압 압력 저하(E-203) 상태에서 생산 지속. 유압 필터 막힘으로 메인 압력이 21MPa → 17MPa로 떨어졌으나 경보 리셋 후 재가동.",
     "해당 로트 전량 회수·선별. E-203 발생 시 품질팀 통보와 초품 재검사를 의무화. 필터 교체 주기 300시간으로 단축(설비보전팀 협의)."),
    ("QR-2026-004", "CNC 4호기 표면 조도 불량", "CNC-04", "E-202", "2026-06-05",
     "가공면 조도 Ra 3.2 초과(기준 Ra 1.6) 130개.", "절삭유 압력 저하(E-202)로 냉각 부족.",
     "절삭유 필터 교체, 압력 모니터링 주기 단축."),
    ("QR-2026-005", "프레스 5호기 균열 발생", "PRESS-05", "E-101", "2026-08-11",
     "성형부 미세 균열 35개.", "소재 로트 연신율 미달(공급사 원인). 같은 시기 모터 과부하(E-101) 2회 발생했으나 직접 원인 아님.",
     "공급사 시정 조치 요구(SCAR), 소재 수입검사 강화."),
]


def write_regulations_and_reports():
    for doc_id, title, dept, level, ver, body in REGULATIONS:
        meta = {"doc_id": doc_id, "title": title, "dept": dept, "access_level": level, "version": ver}
        (DOCS / f"{doc_id}.md").write_text(front_matter(meta) + body.strip() + "\n", encoding="utf-8")
    for doc_id, title, eq_id, code, day, symptom, cause, action in QUALITY_REPORTS:
        meta = {"doc_id": doc_id, "title": title, "dept": "품질팀", "access_level": "quality",
                "version": "1.0", "equipment_id": eq_id}
        body = (f"# 품질 불량 보고서 {doc_id}: {title}\n\n"
                f"## 1. 개요\n- 발생일: {day} / 설비: {eq_id} / 관련 경보: {code}\n\n"
                f"## 2. 불량 현상\n{symptom}\n\n## 3. 원인 분석\n{cause}\n\n## 4. 조치 및 재발 방지\n{action}\n\n"
                "## 5. 배포 범위\n품질팀, 관리자 (사내 대외비)\n")
        (DOCS / f"{doc_id}.md").write_text(front_matter(meta) + body, encoding="utf-8")


def write_csv(name, header, rows):
    with open(CSVS / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_csvs():
    write_csv("equipment", ["equipment_id", "name", "type", "line", "model", "install_year"],
              [[e[k] for k in ("equipment_id", "name", "type", "line", "model", "install_year")] for e in EQUIPMENT])
    write_csv("alarm_codes", ["equipment_type", "code", "title", "category", "severity"],
              [[t, a[0], a[1], a[2], a[3]] for t, al in ALARMS.items() for a in al])
    write_csv("parts", ["part_no", "name", "category"], PARTS)
    write_csv("stock", ["part_no", "qty", "min_qty", "location"],
              [[p[0], 0 if p[0] == "P-HYD-002" else random.randint(1, 30), random.choice([2, 3, 5]),
                f"자재창고 {random.choice('ABC')}-{random.randint(1, 12):02d}"] for p in PARTS])
    write_csv("alarm_parts", ["equipment_type", "code", "part_no"],
              [[t, a[0], p] for t, al in ALARMS.items() for a in al for p in a[6]])
    rows = [[e["equipment_id"], a[0], f"MAN-{e['equipment_id']}"] for e in EQUIPMENT for a in ALARMS[e["type"]]]
    rows += [[q[2], q[3], q[0]] for q in QUALITY_REPORTS]
    write_csv("alarm_documents", ["equipment_id", "code", "doc_id"], rows)

    # 정비 이력 200건: 최근 1년, 3호기 E-203은 최근에 반복되도록 고정 이벤트 포함
    fixed = [("PRESS-03", "E-203", d, desc, parts, dt) for d, desc, parts, dt in [
        ("2026-09-18", "메인 압력 17MPa로 저하. 유압 필터 차압 적색. 필터 엘리먼트 교체 후 21MPa 회복.", "P-HYD-003", 95),
        ("2026-08-02", "압력 저하 경보. 펌프 축 씰 누유 확인, 씰 키트 교체.", "P-HYD-001", 240),
        ("2026-06-27", "경보 발생했으나 게이지 정상. 압력 센서 출력 불안정, 센서 교체.", "P-HYD-002", 80),
        ("2026-05-21", "유압 필터 막힘. 필터 교체.", "P-HYD-003", 70),
    ]]
    rows, seq = [], 1
    for eq_id, code, d, desc, parts, dt in fixed:
        rows.append([f"MH-{seq:04d}", eq_id, d, code, "고장수리", desc, parts, dt, "정비원 M03"])
        seq += 1
    while len(rows) < 200:
        eq = random.choice(EQUIPMENT)
        day = TODAY - timedelta(days=random.randint(1, 365))
        if random.random() < 0.35:
            rows.append([f"MH-{seq:04d}", eq["equipment_id"], day.isoformat(), "", "예방정비",
                         random.choice(["월간 점검 실시, 이상 없음", "필터 차압 점검 및 청소", "안전장치 기능 시험 합격",
                                        "전기 단자 조임 점검"]), "", random.randint(20, 60),
                         f"정비원 M0{random.randint(1, 6)}"])
        else:
            a = random.choice(ALARMS[eq["type"]])
            if eq["equipment_id"] == "PRESS-03" and a[0] == "E-203":
                continue  # 3호기 E-203은 위 고정 이벤트로만 관리
            part = random.choice(a[6])
            rows.append([f"MH-{seq:04d}", eq["equipment_id"], day.isoformat(), a[0], "고장수리",
                         f"{a[1]} 경보. {random.choice(a[4])} 확인 후 조치.", part, random.randint(30, 300),
                         f"정비원 M0{random.randint(1, 6)}"])
        seq += 1
    rows.sort(key=lambda r: r[2], reverse=True)
    write_csv("maintenance_history", ["record_id", "equipment_id", "work_date", "alarm_code", "work_type",
                                      "description", "parts_used", "downtime_min", "technician"], rows)


if __name__ == "__main__":
    DOCS.mkdir(parents=True, exist_ok=True)
    CSVS.mkdir(parents=True, exist_ok=True)
    write_manuals()
    write_regulations_and_reports()
    write_csvs()
    print(f"문서 {len(list(DOCS.glob('*.md')))}개, CSV {len(list(CSVS.glob('*.csv')))}개 생성 → {ROOT}")
