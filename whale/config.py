"""config.py — 路径与参数（自动探测 + config.json 覆盖）。

默认约定：
  JONSBO AIO 安装在 %LOCALAPPDATA%\\JONSBO-AIO
  主题目录在  <JONSBO>\\Programme\\<theme_name>
  立绘素材在  %USERPROFILE%\\.dsh\\profiles\\*\\node_modules\\dsh-whale-musume\\assets\\generated
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"

DEFAULTS = {
    "jonsbo_dir": "",       # 空 = %LOCALAPPDATA%\JONSBO-AIO
    "theme_name": "WhaleGirl",
    "assets_dir": "",       # 空 = 自动探测 dsh-whale-musume
    "port": 8765,
    "fps": 10,
    "font_bold": "",
    "font_regular": "",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def jonsbo_dir() -> Path:
    cfg = load()
    if cfg.get("jonsbo_dir"):
        return Path(cfg["jonsbo_dir"])
    return Path(os.environ["LOCALAPPDATA"]) / "JONSBO-AIO"


def theme_name() -> str:
    return load().get("theme_name") or "WhaleGirl"


def theme_dir() -> Path:
    return jonsbo_dir() / "Programme" / theme_name()


def assets_dir() -> str:
    """dsh-whale-musume 的 assets/generated 目录。"""
    cfg = load()
    if cfg.get("assets_dir"):
        return cfg["assets_dir"]
    patterns = [
        os.path.expandvars(r"%USERPROFILE%\.dsh\profiles\*\node_modules\dsh-whale-musume\assets\generated"),
        os.path.expandvars(r"%APPDATA%\*\node_modules\dsh-whale-musume\assets\generated"),
    ]
    for pat in patterns:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return ""


def fonts() -> tuple[str, str]:
    """返回 (粗体, 常规) 字体路径，找不到时回落到黑体。"""
    cfg = load()
    bold = cfg.get("font_bold") or r"C:\Windows\Fonts\msyhbd.ttc"
    regular = cfg.get("font_regular") or r"C:\Windows\Fonts\msyh.ttc"
    if not os.path.isfile(bold):
        bold = r"C:\Windows\Fonts\simhei.ttf"
    if not os.path.isfile(regular):
        regular = bold
    return bold, regular


def port() -> int:
    return int(load().get("port") or 8765)


def fps() -> int:
    return int(load().get("fps") or 10)


def device_sn() -> str:
    """从 JONSBO AIO 的 Config.json 读设备序列号（用于注册主题）。"""
    p = (Path(os.environ["APPDATA"]) / "Hailian Zhixin (Shenzhen) Technology Co., Ltd"
         / "JONSBO-AIO" / "Config.json")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        for d in data.get("DeviceConfigs", []):
            if d.get("SN"):
                return d["SN"]
    except Exception:
        pass
    return ""
