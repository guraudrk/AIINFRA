#!/usr/bin/env python3
"""Grafana 대시보드 JSON 생성기 → charts/ai-platform/dashboards/*.json

패널을 (제목, 종류, PromQL 목록, 단위, 범례, 임계값) 한 줄로 정의한다.
  python3 scripts/gen_dashboards.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "charts" / "ai-platform" / "dashboards"
DS = {"type": "prometheus", "uid": "prometheus"}


def panel(pid, title, kind, exprs, unit="short", w=8, h=7, threshold=None, legends=None):
    targets = [{"datasource": DS, "expr": e, "legendFormat": (legends or [""] * len(exprs))[i], "refId": chr(65 + i)}
               for i, e in enumerate(exprs)]
    steps = [{"color": "green", "value": None}]
    if threshold is not None:
        steps.append({"color": "red", "value": threshold})
    p = {"id": pid, "title": title, "type": kind, "datasource": DS, "targets": targets,
         "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
         "options": {}}
    if kind == "timeseries" and threshold is not None:
        p["fieldConfig"]["defaults"]["custom"] = {"thresholdsStyle": {"mode": "line"}}
    return p, w, h


def dashboard(uid, title, panels):
    out, x, y, row_h = [], 0, 0, 0
    for p, w, h in panels:  # 24칸 격자에 왼쪽부터 채운다
        if x + w > 24:
            x, y, row_h = 0, y + row_h, 0
        p["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
        out.append(p)
        x += w
        row_h = max(row_h, h)
    return {"uid": uid, "title": title, "schemaVersion": 39, "version": 1, "editable": True,
            "time": {"from": "now-1h", "to": "now"}, "refresh": "15s", "tags": ["ax-platform-lab"],
            "panels": out}


ai_platform = dashboard("ax-ai-platform", "AX · AI 플랫폼 (GPU·LLM)", [
    panel(1, "GPU 사용률", "timeseries", ["DCGM_FI_DEV_GPU_UTIL"], "percent", legends=["GPU {{gpu}}"]),
    panel(2, "GPU 온도 (알람 85℃)", "timeseries", ["DCGM_FI_DEV_GPU_TEMP"], "celsius", threshold=85,
          legends=["GPU {{gpu}}"]),
    panel(3, "GPU 메모리 사용률 (알람 90%)", "timeseries",
          ["DCGM_FI_DEV_FB_USED / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE) * 100"], "percent", threshold=90,
          legends=["GPU {{gpu}}"]),
    panel(4, "GPU 전력", "timeseries", ["DCGM_FI_DEV_POWER_USAGE"], "watt", legends=["GPU {{gpu}}"]),
    panel(5, "마지막 Xid (0=정상)", "stat", ["max by (gpu) (DCGM_FI_DEV_XID_ERRORS)"], threshold=1,
          legends=["GPU {{gpu}}"]),
    panel(6, "처리 중 LLM 요청 (대기열, 슬롯 4)", "timeseries", ["sum(ax_llm_inflight)"], threshold=4,
          legends=["in-flight"]),
    panel(7, "TTFT p50 / p95 (알람 p95 5초)", "timeseries",
          ["histogram_quantile(0.5, sum by (le) (rate(ax_llm_ttft_seconds_bucket[5m])))",
           "histogram_quantile(0.95, sum by (le) (rate(ax_llm_ttft_seconds_bucket[5m])))"], "s", threshold=5,
          legends=["p50", "p95"]),
    panel(8, "생성 속도 p50 (토큰/초)", "timeseries",
          ["histogram_quantile(0.5, sum by (le) (rate(ax_llm_tokens_per_second_bucket[5m])))"], legends=["p50"]),
    panel(9, "LLM 호출 시간 p95", "timeseries",
          ["histogram_quantile(0.95, sum by (le) (rate(ax_llm_duration_seconds_bucket[5m])))"], "s",
          legends=["p95"]),
    panel(10, "노드 CPU 사용률", "timeseries",
          ['100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])))'], "percent", w=12,
          legends=["{{instance}}"]),
    panel(11, "노드 메모리 사용률", "timeseries",
          ["100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"], "percent", w=12,
          legends=["{{instance}}"]),
])

service_ops = dashboard("ax-service-ops", "AX · 서비스 운영 (사용자·권한·데이터)", [
    panel(1, "역할별 요청 수 (/분)", "timeseries", ["sum by (role) (rate(ax_requests_total[5m])) * 60"],
          legends=["{{role}}"]),
    panel(2, "권한 거부 (/10분)", "timeseries", ["sum by (role, tool) (increase(ax_permission_denied_total[10m]))"],
          threshold=10, legends=["{{role}} → {{tool}}"]),
    panel(3, "검색 근거 0건 비율 (1시간)", "stat",
          ["sum(increase(ax_search_empty_total[1h])) / clamp_min(sum(increase(ax_search_total[1h])), 1)"],
          "percentunit", threshold=0.3),
    panel(4, "응답 결과 (answered / unknown / error)", "timeseries",
          ["sum by (result) (rate(ax_requests_total[5m])) * 60"], legends=["{{result}}"]),
    panel(5, "입구 5xx 비율 (알람 2%)", "timeseries",
          ['sum(rate(traefik_service_requests_total{code=~"5.."}[5m])) / clamp_min(sum(rate(traefik_service_requests_total[5m])), 1e-9)'],
          "percentunit", threshold=0.02, legends=["5xx"]),
    panel(6, "응답 시간 p95 (게이트웨이)", "timeseries",
          ["histogram_quantile(0.95, sum by (le) (rate(ax_request_duration_seconds_bucket[5m])))"], "s",
          legends=["p95"]),
    panel(7, "DB 연결 수", "timeseries", ['sum by (datname) (pg_stat_database_numbackends{datname="hanbit"})'],
          legends=["{{datname}}"]),
    panel(8, "PVC 사용률 (kind local-path는 수집 안 됨)", "timeseries",
          ["100 * kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes"], "percent", threshold=80,
          legends=["{{persistentvolumeclaim}}"]),
    panel(9, "마지막 DB 백업 성공", "stat",
          ['kube_cronjob_status_last_successful_time{cronjob="pg-backup"} * 1000'], "dateTimeFromNow"),
    panel(10, "발생 중인 알람", "stat", ['count(ALERTS{alertstate="firing", severity=~"critical|warning"}) or vector(0)'],
          threshold=1, w=6),
    panel(11, "Pod 재시작 (15분)", "timeseries",
          ['sum by (pod) (increase(kube_pod_container_status_restarts_total{namespace="ai-platform"}[15m]))'],
          w=18, legends=["{{pod}}"]),
])

OUT.mkdir(parents=True, exist_ok=True)
for name, dash in (("ai-platform", ai_platform), ("service-ops", service_ops)):
    (OUT / f"{name}.json").write_text(json.dumps(dash, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{name}.json: 패널 {len(dash['panels'])}개")
