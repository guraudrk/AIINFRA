"""GPU 지표 시뮬레이터 (SIMULATED 모드용 DCGM exporter 대역).

실제 NVIDIA dcgm-exporter와 같은 지표 이름·라벨을 내보내므로, 대시보드와 알람을
REAL GPU 환경(dcgm-exporter)에 그대로 옮길 수 있다.

  GPU 0 = llm-serving,  GPU 1 = embedding-serving  (가상 NVIDIA L40S 48GB)
  사용률  ← 게이트웨이의 ax_llm_inflight (처리 중인 LLM 호출 수)
  메모리  ← Ollama /api/ps 의 모델 VRAM 크기 + KV 캐시 여유
  온도·전력 ← 사용률을 따라 천천히 변화

장애 주입 (M8):
  curl -X POST localhost:9400/fault -d '{"type":"overheat"}'   # 온도 92℃
  curl -X POST localhost:9400/fault -d '{"type":"xid79"}'      # Xid 79: GPU가 PCIe 버스에서 떨어짐
  curl -X POST localhost:9400/fault -d '{"type":"clear"}'
"""
import json
import os
import random
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY = os.environ.get("GATEWAY_METRICS", "http://ax-gateway:8000/metrics")
SERVING = {0: os.environ.get("LLM_URL", "http://llm-serving:11434"),
           1: os.environ.get("EMBED_URL", "http://embedding-serving:11434")}
HOST = os.environ.get("NODE_NAME", "gpu-node")
FB_TOTAL_MIB = 46068          # L40S 48GB의 nvidia-smi 표시 용량
TDP_W = 350

state = {g: {"util": 0.0, "temp": 34.0, "power": 30.0, "fb_used": 0.0, "xid": 0} for g in (0, 1)}
fault = {"type": None}
lock = threading.Lock()


def fetch(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode()


def inflight():
    try:
        m = re.search(r"^ax_llm_inflight (\S+)", fetch(GATEWAY), re.M)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def model_vram_mib(gpu):
    try:
        models = json.loads(fetch(f"{SERVING[gpu]}/api/ps")).get("models", [])
        size = sum(m.get("size_vram") or m.get("size", 0) for m in models)  # CPU 추론이면 size_vram=0 → size 사용
        return size / 2**20
    except Exception:
        return 0.0


def tick():
    """5초마다 목표값을 계산하고 온도는 천천히 따라가게 한다(실제 GPU처럼 열관성)."""
    while True:
        busy = inflight()
        with lock:
            for g, s in state.items():
                target_util = min(100.0, busy * 45) if g == 0 else min(30.0, busy * 5)
                target_util += random.uniform(0, 3)
                s["fb_used"] = model_vram_mib(g) * 1.15   # 모델 가중치 + KV 캐시·런타임 여유 15%
                if fault["type"] == "xid79" and g == 0:
                    s.update(util=0.0, fb_used=0.0, power=0.0, xid=79)   # 버스 이탈: 연산 불가
                    continue
                s["util"] = target_util
                target_temp = 92.0 if (fault["type"] == "overheat" and g == 0) else 34 + s["util"] * 0.45
                s["temp"] += (target_temp - s["temp"]) * 0.3
                s["power"] = 30 + s["util"] / 100 * (TDP_W - 30)
                if fault["type"] is None:
                    s["xid"] = 0
        time.sleep(5)


def render():
    lines = []
    metrics = [("DCGM_FI_DEV_GPU_UTIL", "gauge", "GPU utilization (%)", "util"),
               ("DCGM_FI_DEV_GPU_TEMP", "gauge", "GPU temperature (C)", "temp"),
               ("DCGM_FI_DEV_POWER_USAGE", "gauge", "Power draw (W)", "power"),
               ("DCGM_FI_DEV_FB_USED", "gauge", "Framebuffer memory used (MiB)", "fb_used"),
               ("DCGM_FI_DEV_FB_FREE", "gauge", "Framebuffer memory free (MiB)", "fb_free"),
               ("DCGM_FI_DEV_XID_ERRORS", "gauge", "Value of the last XID error encountered", "xid")]
    with lock:
        for name, mtype, help_, key in metrics:
            lines += [f"# HELP {name} {help_}", f"# TYPE {name} {mtype}"]
            for g, s in state.items():
                val = FB_TOTAL_MIB - s["fb_used"] if key == "fb_free" else s[key]
                labels = (f'gpu="{g}",UUID="GPU-SIM-0000-000{g}",device="nvidia{g}",'
                          f'modelName="NVIDIA L40S (simulated)",Hostname="{HOST}"')
                lines.append(f"{name}{{{labels}}} {val:.1f}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render().encode() if self.path == "/metrics" else b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/fault":
            self.send_response(404); self.end_headers(); return
        kind = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}").get("type")
        fault["type"] = None if kind in (None, "clear") else kind
        self.send_response(200); self.end_headers()
        self.wfile.write(f"fault={fault['type']}\n".encode())
        print(json.dumps({"event": "fault", "type": fault["type"]}), flush=True)

    def log_message(self, *args):  # 접근 로그 생략 (Prometheus가 15초마다 호출)
        pass


if __name__ == "__main__":
    threading.Thread(target=tick, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 9400), Handler).serve_forever()
