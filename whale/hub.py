"""hub.py — 多 Agent 状态中枢：每个上报者一条记录，按优先级 + 租约合成屏幕状态。"""
from __future__ import annotations

import threading
import time

PRIORITY = {"approval": 100, "question": 90, "plan": 70, "working": 40, "done": 30, "idle": 10}
TTL = {"approval": 300.0, "question": 300.0, "plan": 120.0, "working": 60.0,
       "done": 10.0, "idle": 30.0}
VALID = set(PRIORITY)


class Hub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reports: dict[str, dict] = {}

    def report(self, source: str, state: str, detail: str = "", session: str = "",
               ttl: float | None = None, priority: int | None = None) -> str:
        state = (state or "").strip().lower()
        if state not in VALID:
            raise ValueError("unknown state: %r" % state)
        now = time.time()
        key = "%s/%s" % (source or "unknown", session or "-")
        with self._lock:
            self._reports[key] = {
                "source": (source or "unknown")[:16],
                "session": session or "",
                "state": state,
                "detail": detail or "",
                "priority": int(priority) if priority is not None else PRIORITY[state],
                "expires": now + float(ttl if ttl is not None else TTL[state]),
                "updated": now,
            }
        return key

    def clear(self, source: str | None = None, session: str | None = None) -> int:
        with self._lock:
            if not source:
                n = len(self._reports)
                self._reports.clear()
                return n
            n = 0
            for k in list(self._reports):
                r = self._reports[k]
                if r["source"] == source and (session is None or r["session"] == session):
                    self._reports.pop(k, None)
                    n += 1
            return n

    def _sweep(self, now: float) -> None:
        for k in list(self._reports):
            if self._reports[k]["expires"] <= now:
                self._reports.pop(k, None)

    def compose(self, now: float | None = None) -> dict:
        now = now or time.time()
        with self._lock:
            self._sweep(now)
            items = sorted(self._reports.values(),
                           key=lambda r: (r["priority"], r["updated"]), reverse=True)
        if not items:
            return {"state": "idle", "detail": "", "source": "", "count": 0}
        top = items[0]
        return {"state": top["state"], "detail": top["detail"],
                "source": top["source"], "count": len(items) - 1}

    def snapshot(self, now: float | None = None) -> dict:
        now = now or time.time()
        with self._lock:
            self._sweep(now)
            items = [dict(r) for r in sorted(self._reports.values(),
                                             key=lambda r: (r["priority"], r["updated"]),
                                             reverse=True)]
        head = items[0] if items else {"state": "idle", "detail": "", "source": ""}
        return {"state": head["state"], "detail": head["detail"],
                "source": head["source"], "count": max(0, len(items) - 1),
                "reports": items, "ts": now}
