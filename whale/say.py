"""say.py — 命令行客户端（优先走本地 HTTP 接口，接口没开就退回写 cmd.json）。

  say.py "开会中" "13:00-14:00 勿扰" [秒数] [--mood work-meeting]
  say.py --image 图片.png [秒数]
  say.py --resume
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CMD = HERE / "cmd.json"
import config

BASE = "http://127.0.0.1:%d" % config.port()

sys.path.insert(0, str(HERE))
from moods import pick_mood  # noqa: E402


def post(path, payload) -> bool:
    try:
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        print("api ->", body.get("applied", body))
        return True
    except Exception:
        return False


def fallback(payload):
    tmp = CMD.with_suffix(".cmd.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CMD)
    print("file ->", payload)


def send(path, payload, fallback_payload):
    if not post(path, payload):
        fallback(fallback_payload)


if __name__ == "__main__":
    args = sys.argv[1:]
    mood = None
    if "--mood" in args:
        i = args.index("--mood")
        mood = args[i + 1]
        del args[i:i + 2]

    if "--resume" in args:
        send("/resume", {}, {"type": "resume"})
    elif "--image" in args:
        i = args.index("--image")
        path = args[i + 1]
        dur = float(args[i + 2]) if len(args) > i + 2 else 180
        payload = {"path": path, "seconds": dur}
        fallback_payload = {"type": "image", "path": path,
                            "until": (time.time() + dur) if dur > 0 else 4102444800}
        send("/image", payload, fallback_payload)
    else:
        text = args[0] if args else "你好，我是 DeepSeek"
        sub = args[1] if len(args) > 1 else ""
        dur = float(args[2]) if len(args) > 2 else 180
        m = mood or pick_mood(text + " " + sub)
        payload = {"text": text, "sub": sub, "mood": m, "seconds": dur}
        fallback_payload = {"type": "text", "text": text, "sub": sub, "mood": m,
                            "until": (time.time() + dur) if dur > 0 else 4102444800}
        send("/say", payload, fallback_payload)
