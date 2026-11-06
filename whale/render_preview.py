"""render_preview.py — 生成 README / docs 用的效果图。

用法：python render_preview.py
输出：../docs/images/{idle,working,approval,question}.png
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import daemon as D  # noqa: E402

OUT = HERE.parent / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)

# 待机：挑一个“乖巧站姿”的时间点（动作从 2s 开始，这里取 0.6s）
IDLE_T = 0.6
NOW = datetime(2026, 11, 6, 10, 24)


def frame(state=None, detail="", bubble=None):
    if bubble:
        D.show_bubble(bubble, hold=10 ** 9, key="preview")
    else:
        D.BUBBLE["text"] = ""
        D.BUBBLE["until"] = 0
    status = {"state": state or "idle", "detail": detail}
    return D.idle_frame(IDLE_T, NOW, status)


def main():
    shots = {
        "idle.png": frame(),
        "working.png": frame("working", "终端", "终端在跑，稍等喵～"),
        "approval.png": frame("approval", "允许本次操作使用完全权限", "这个要你点头哦"),
        "question.png": frame("question", "要用哪种方案？", "有个问题要你选～"),
    }
    for name, img in shots.items():
        img.save(OUT / name)
        print("saved", OUT / name)


if __name__ == "__main__":
    main()
