"""make_theme.py — 创建/注册 WhaleGirl 自定义主题。

JONSBO AIO 启动时会加载 `Programme\\<主题名>\\` 下的主题，
并在 `ThemeScheme\\<设备SN>\\` 里记录“已安装”。本脚本把两处都准备好。

用法：
    python make_theme.py            # 创建并注册
    python make_theme.py --force    # 覆盖已有主题文件
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config

W, H = 960, 376


def _frame(font_bold: str) -> Image.Image:
    img = Image.new("RGB", (W, H), (10, 14, 28))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=(int(10 + 16 * t), int(14 + 20 * t), int(30 + 36 * t)))
    d.rectangle([0, 0, W, 4], fill=(72, 190, 255))
    text = "WhaleGirl"
    size = 64
    f = ImageFont.truetype(font_bold, size)
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, H / 2 - size / 2 - 20), text, font=f, fill=(235, 245, 255))
    sub = "主题已就绪，启动 daemon.py 后这里会变成鲸鱼娘"
    f2 = ImageFont.truetype(font_bold, 22)
    sw = d.textlength(sub, font=f2)
    d.text(((W - sw) / 2, H / 2 + 40), sub, font=f2, fill=(120, 200, 240))
    return img


def main() -> None:
    force = "--force" in sys.argv
    theme = config.theme_name()
    tdir = config.theme_dir()
    if tdir.exists() and not force:
        print("theme exists:", tdir, "(use --force to overwrite)")
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "source").mkdir(exist_ok=True)

    bold, _ = config.fonts()
    img = _frame(bold)
    for name in ("data.png", "back.png", "demo.png"):
        img.save(tdir / name)
    img.save(tdir / "source" / "data.png")
    img.save(tdir / "source" / "back.png")

    (tdir / "Setting.txt").write_text(
        "name:%s\nwidth:%d\nheight:%d\ndata.png:x@0,y@0,z@-1\n" % (theme, W, H),
        encoding="utf-8")

    meta = {
        "Type": 1, "Name": theme, "Width": float(W), "Height": float(H),
        "FillMode": 0, "CropArea": "0, 0, 0, 0", "ThumbnailImageData": "",
        "DisplayDirection": 0, "FontDirection": 0,
        "BackgroundImage": None, "BackgroundVideoFile": None, "OriginalBGPath": None,
        "DisplayTexts": [], "DisplayImages": [], "TouchPoints": [],
        "ShutDownCancelPoint": {"TPType": 0, "IconPath": None, "Content": None,
                                "X1": 0, "X2": 0, "Y1": 0, "Y2": 0},
        "IsTouch": 0, "IsApp": 0,
    }
    (tdir / ("%s.json" % theme)).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    sn = config.device_sn()
    if sn:
        deploy = config.jonsbo_dir() / "ThemeScheme" / sn
        deploy.mkdir(parents=True, exist_ok=True)
        deployed = dict(meta, IsDefault=True, Isup=True)
        (deploy / ("%s.json" % theme)).write_text(
            json.dumps(deployed, ensure_ascii=False), encoding="utf-8")
        print("registered for device:", sn)
    else:
        print("warning: device SN not found (is JONSBO AIO installed once?)")

    print("theme ready:", tdir)
    print("next: 1) 重启 JONSBO AIO  2) 在主题列表选 %s  3) python daemon.py" % theme)


if __name__ == "__main__":
    main()
