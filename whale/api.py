"""api.py — 本地 HTTP 接口（默认 127.0.0.1:8765）。

POST /say     {"text":"开会中","sub":"14:00-15:00","mood":"work-meeting","seconds":600}
POST /image   {"path":"C:/pics/a.png","seconds":30}
POST /state   {"state":"working|approval|question|plan|idle","detail":"pwsh"}
POST /resume
GET  /health
GET  /       （用法说明）

允许跨源（DSH Web UI 在另一个端口，需要浏览器端 fetch）。
"""
import json
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from moods import pick_mood

USAGE = {
    "endpoints": {
        "POST /say": {"text": "必填", "sub": "可选", "mood": "可选，不填按关键词自动",
                      "seconds": "可选，0=一直显示直到 resume，默认 180"},
        "POST /image": {"path": "必填", "seconds": "可选，默认 30"},
        "POST /report": {"source": "Agent 标识，如 dsh/reasonix/hermes/teleagent",
                         "session": "可选，区分同 Agent 多会话",
                         "state": "working|approval|question|plan|done|idle",
                         "detail": "可选", "ttl": "秒，可选", "priority": "可选"},
        "POST /state": {"state": "working|approval|question|plan|idle",
                        "detail": "可选，显示在卡片上",
                        "source": "可选，默认 manual", "ttl": "秒，可选"},
        "POST /clear": {"source": "必填", "session": "可选"},
        "POST /flash": {"kind": "success|failure", "seconds": "默认 3"},
        "POST /resume": {},
        "GET /health": {},
    }
}

STATE_ALIASES = {
    "working": "working", "busy": "working", "running": "working",
    "approval": "approval", "approve": "approval", "pending-approval": "approval",
    "question": "question", "ask": "question", "pending-question": "question",
    "plan": "plan", "plan-review": "plan",
    "idle": "idle", "": "idle",
}


def make_handler(write_cmd, log, hub=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "WhaleGirl/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()

        def _read_status(self):
            try:
                p = HERE / "status.json"
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {"state": "unknown", "detail": "", "ts": time.time()}

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/health":
                self._send(200, {"ok": True, "ts": time.time()})
            elif path == "/state":
                if hub is not None:
                    self._send(200, hub.snapshot())
                else:
                    self._send(200, self._read_status())
            else:
                self._send(200, USAGE)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
            except Exception as e:
                return self._send(400, {"ok": False, "error": "invalid json: %s" % e})

            path = self.path.split("?")[0]
            try:
                if path == "/say":
                    text = data.get("text", "")
                    sub = data.get("sub", "")
                    if not text:
                        return self._send(400, {"ok": False, "error": "text is required"})
                    seconds = float(data.get("seconds", 180) or 0)
                    payload = {
                        "type": "text",
                        "text": text,
                        "sub": sub,
                        "mood": data.get("mood") or pick_mood(text + " " + sub),
                        "until": (time.time() + seconds) if seconds > 0 else 4102444800,
                    }
                elif path == "/image":
                    p = data.get("path", "")
                    if not p:
                        return self._send(400, {"ok": False, "error": "path is required"})
                    seconds = float(data.get("seconds", 30) or 0)
                    payload = {"type": "image", "path": p,
                               "until": (time.time() + seconds) if seconds > 0 else 4102444800}
                elif path in ("/state", "/report"):
                    state = STATE_ALIASES.get(str(data.get("state", "")).strip().lower())
                    if state is None:
                        return self._send(400, {"ok": False, "error": "unknown state",
                                                "allowed": sorted(set(STATE_ALIASES.values()))})
                    source = str(data.get("source") or "manual")[:16]
                    session = str(data.get("session") or "")
                    detail = str(data.get("detail", ""))
                    ttl = data.get("ttl")
                    priority = data.get("priority")
                    if data.get("force"):
                        priority = 999
                    if hub is not None:
                        hub.report(source, state, detail, session, ttl, priority)
                        return self._send(200, {"ok": True, "key": "%s/%s" % (source, session or "-"),
                                                "state": state,
                                                "display": hub.compose()})
                    payload = {"type": "state", "state": state, "detail": detail,
                               "source": source, "session": session,
                               "ttl": ttl, "priority": priority,
                               "force": bool(data.get("force"))}

                elif path == "/clear":
                    source = str(data.get("source") or "")
                    if not source:
                        return self._send(400, {"ok": False, "error": "source required"})
                    session = data.get("session")
                    if hub is not None:
                        n = hub.clear(source, str(session) if session is not None else None)
                        return self._send(200, {"ok": True, "removed": n,
                                                "display": hub.compose()})
                    payload = {"type": "clear", "source": source,
                               "session": str(session or "")}
                elif path == "/flash":
                    kind = str(data.get("kind", "success")).lower()
                    if kind not in ("success", "failure"):
                        return self._send(400, {"ok": False, "error": "kind must be success|failure"})
                    payload = {"type": "flash", "kind": kind,
                               "seconds": float(data.get("seconds", 3) or 3)}
                elif path == "/resume":
                    payload = {"type": "resume"}
                else:
                    return self._send(404, {"ok": False, "error": "unknown endpoint", **USAGE})
            except Exception as e:
                return self._send(400, {"ok": False, "error": str(e)})

            write_cmd(payload)
            log("api %s -> %s" % (path, payload))
            self._send(200, {"ok": True, "applied": payload})

    return Handler


def start(write_cmd, log, hub=None, host="127.0.0.1", port=8765):
    handler = make_handler(write_cmd, log, hub)
    httpd = ThreadingHTTPServer((host, port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True, name="whale-api")
    t.start()
    log("api listening on http://%s:%d" % (host, port))
    return httpd
