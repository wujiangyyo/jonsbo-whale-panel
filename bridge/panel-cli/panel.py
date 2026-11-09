"""panel.py — 副屏命令行客户端，给没有 MCP 的 Agent / hook 用。

用法：
    python panel.py working "运行测试" --source hermes --ttl 60
    python panel.py approval "要删除文件" --source hermes
    python panel.py question "选哪个方案" --source hermes
    python panel.py clear --source hermes
    python panel.py status
    python panel.py say "开会中" --sub "14:00 前勿扰" --seconds 600
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

API = os.environ.get("PANEL_API", "http://127.0.0.1:8765").rstrip("/")


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(API + path, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(description="鲸鱼娘副屏命令行")
    ap.add_argument("action", choices=["working", "approval", "question", "plan",
                                       "done", "idle", "clear", "status", "say", "resume"])
    ap.add_argument("text", nargs="?", default="", help="detail 或 say 的主标题")
    ap.add_argument("--source", default=os.environ.get("PANEL_SOURCE", "manual"))
    ap.add_argument("--session", default="")
    ap.add_argument("--ttl", type=float, default=None)
    ap.add_argument("--priority", type=int, default=None)
    ap.add_argument("--sub", default="")
    ap.add_argument("--seconds", type=float, default=180)
    ap.add_argument("--mark", default="", help="detail 前缀，便于区分（默认源名）")
    a = ap.parse_args()

    detail = (a.mark + a.text) if a.mark else a.text
    try:
        if a.action == "status":
            out = get("/state")
        elif a.action == "clear":
            payload = {"source": a.source}
            if a.session:
                payload["session"] = a.session
            out = post("/clear", payload)
        elif a.action == "resume":
            out = post("/resume", {})
        elif a.action == "say":
            payload = {"text": a.text, "sub": a.sub, "seconds": a.seconds}
            if a.mark:
                payload["text"] = a.mark + a.text
            out = post("/say", payload)
        else:
            payload = {"source": a.source, "session": a.session,
                       "state": a.action, "detail": detail}
            if a.ttl is not None:
                payload["ttl"] = a.ttl
            if a.priority is not None:
                payload["priority"] = a.priority
            out = post("/report", payload)
    except Exception as e:  # noqa: BLE001
        print("panel error: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
