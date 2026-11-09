"""daemon.py — 鲸鱼娘副屏播放器（待机动画 + 时钟 + 文字/图片联动）。

待机：小动作轮播（甩尾/好奇/脸红/招手/眨眼）+ 轻微浮动摆动 + 右侧时钟。
文字：按内容匹配姿态（开会/吃饭/完成/失败/睡觉…），右侧卡片显示文字。
图片：铺满显示。

命令：whale/cmd.json
    {"type":"text","text":"...","sub":"...","mood":"work-meeting","until":<ts>}
    {"type":"image","path":"...","until":<ts>}
    {"type":"resume"}
"""
import io
import json
import math
import os
import random
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
import config

THEME = config.theme_dir()
DATA = THEME / "data.png"
SRC_DATA = THEME / "source" / "data.png"
TMP = THEME / ".data.tmp.png"
CMD = HERE / "cmd.json"
LOG = HERE / "daemon.log"
ASSETS = config.assets_dir()
FONT_BOLD, FONT_REG = config.fonts()
W, H = 960, 376
FPS = config.fps()
CHAR_H = 360
LOOP = 32.0
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 状态模式（由 dsh-panel-bridge 插件上报）
STATUS = {"state": "idle", "detail": "", "source": "", "count": 0}
import hub

HUB = hub.Hub()
STATUS_FILE = HERE / "status.json"


def publish_status():
    """把真实状态写给外部查询（cmd.json 可能停在被忽略的那条）。"""
    try:
        tmp = STATUS_FILE.with_suffix(".status.tmp")
        tmp.write_text(json.dumps({
            "state": STATUS["state"], "detail": STATUS["detail"],
            "source": STATUS.get("source", ""), "count": STATUS.get("count", 0),
            "ts": time.time(), "reports": HUB.snapshot().get("reports", []),
        }, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, STATUS_FILE)
    except Exception:
        pass


STICKY_STATES = {"approval", "question", "plan"}
STICKY_TTL = 180.0
STICKY_UNTIL = 0.0

STATUS_POSE = {"working": "running", "approval": "waiting", "question": "curious", "plan": "thinking"}
# ---------------- 对话气泡 ----------------
BUBBLE = {"text": "", "until": 0.0, "key": ""}
_last_line = {}
_last_bubble_at = {"working": 0.0, "idle": 0.0}
WORK_BUBBLE_COOLDOWN = 25.0
IDLE_CHATTER_GAP = 240.0
BUBBLE_HOLD = 6.0
POSE_BUBBLE_GAP = 30.0
_last_pose = None
_last_pose_bubble = 0.0

LINES = {}
try:
    LINES = json.loads((HERE / "lines.json").read_text(encoding="utf-8"))
except Exception:
    pass


def pick_line(bucket):
    if bucket == "flash_success":
        pool = LINES.get("success") or ["搞定！"]
    elif bucket == "flash_failure":
        pool = LINES.get("failure") or ["报错了…"]
    elif bucket.startswith("pose:"):
        pool = (LINES.get("poses") or {}).get(bucket[5:]) or []
        if not pool:
            return ""
    else:
        pool = LINES.get(bucket) or LINES.get("idle") or ["喵～"]
    i = _last_line.get(bucket, -1) + 1
    _last_line[bucket] = i
    return pool[i % len(pool)]


TOOL_LABELS = {
    "pwsh": "终端", "bash": "终端", "shell": "终端",
    "read": "读文件", "write": "写文件", "edit": "改文件",
    "glob": "找文件", "grep": "搜内容", "ls": "列目录",
    "ask_user_question": "提问", "web_search": "联网搜索", "web_fetch": "读网页",
    "subagent": "子任务", "workflow": "工作流", "present": "展示",
    "todo_write": "列计划", "skill": "加载技能",
}


def normalize_detail(state, detail):
    """把旧版插件发来的原始工具名归一成中文，避免两个窗口来回跳。"""
    d = (detail or "").strip()
    if state == "working" and d in TOOL_LABELS:
        return TOOL_LABELS[d]
    return d


def tool_bucket(detail):
    d = (detail or "").lower()
    if any(k in d for k in ("glob", "grep", "找", "搜", "ls")):
        return "search"
    if any(k in d for k in ("read", "读")):
        return "read"
    if any(k in d for k in ("write", "edit", "写", "改")):
        return "write"
    if any(k in d for k in ("web", "fetch", "联网", "网页")):
        return "web"
    return "working"


def show_bubble(text, hold=BUBBLE_HOLD, key=""):
    log("bubble(%s): %s" % (key or "-", text))
    BUBBLE["text"] = text
    BUBBLE["until"] = time.time() + hold
    BUBBLE["key"] = key


def bubble_active(now=None):
    now = now or time.time()
    return bool(BUBBLE["text"]) and now < BUBBLE["until"]


STATUS_STYLE = {
    "working": ("● 工作中", (80, 200, 255)),
    "approval": ("● 待审批", (255, 110, 110)),
    "question": ("● 等你回答", (255, 200, 90)),
    "plan": ("● 计划待确认", (180, 150, 255)),
}

# (姿态, 持续秒, 之后待机秒)
PLAYLIST = [
    ("tail-swing", 6, 6),
    ("curious", 6, 6),
    ("blush", 4, 8),
    ("greet", 4, 10),
    ("work-idea", 6, 8),
    ("daily-coffee", 6, 10),
    ("meme-peace", 4, 8),
    ("thinking", 6, 8),
    ("daily-stretch", 6, 10),
    ("work-debug", 6, 10),
    ("meme-smug", 4, 8),
    ("weather-umbrella", 6, 11),
    ("daily-gaming", 6, 10),
    ("star", 4, 10),
    ("eat", 6, 11),
    ("pick-up", 4, 10),
    ("meme-heart", 6, 10),
    ("celebrate", 8, 13),
]

ACTIONS = []
_cursor = 2.0
for _name, _dur, _gap in PLAYLIST:
    ACTIONS.append((_cursor, _cursor + _dur, _name))
    _cursor += _dur + _gap
LOOP = round(_cursor, 1)


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")


_scaled = {}


def char(name):
    if name not in _scaled:
        path = os.path.join(ASSETS, "dsh-whale-state-%s.webp" % name)
        if not os.path.isfile(path):
            path = os.path.join(ASSETS, "dsh-whale-state-idle-cute.webp")
        im = Image.open(path).convert("RGBA")
        s = CHAR_H / im.height
        _scaled[name] = im.resize((int(im.width * s), CHAR_H), Image.LANCZOS)
    return _scaled[name]


BACKGROUND = None


def background():
    global BACKGROUND
    if BACKGROUND is None:
        img = Image.new("RGB", (W, H), (6, 12, 24))
        d = ImageDraw.Draw(img)
        for y in range(H):
            t = y / (H - 1)
            d.line([(0, y), (W, y)], fill=(int(6 + 10 * t), int(12 + 34 * t), int(24 + 52 * t)))
        glow = Image.new("L", (W, H), 0)
        ImageDraw.Draw(glow).ellipse([-140, -90, 640, 480], fill=95)
        glow = glow.filter(ImageFilter.GaussianBlur(95))
        BACKGROUND = Image.composite(Image.new("RGB", (W, H), (40, 120, 190)), img,
                                     glow.point(lambda v: int(v * 0.55)))
        # 静止气泡纹理
        import random as _r
        rnd = _r.Random(7)
        d = ImageDraw.Draw(BACKGROUND, "RGBA")
        for _ in range(60):
            x = rnd.uniform(0, W)
            y = rnd.uniform(0, H)
            r = rnd.uniform(1.0, 4.0)
            a = rnd.randint(18, 55)
            d.ellipse([x - r, y - r, x + r, y + r], outline=(150, 220, 255, a), width=1)
    return BACKGROUND


# 气泡按相位预渲染（4 秒 24 个相位），之后只做遮罩粘贴
_rnd = random.Random(42)
_BUBBLES = [(_rnd.uniform(0, W), 26 * _rnd.choice([0.25, 0.5, 0.75, 1.0]),
             _rnd.uniform(0, H + 40), _rnd.uniform(1.2, 4.2), _rnd.uniform(0, 6.28))
            for _ in range(46)]
_bubble_cache = {}


def bubble_layer(phase):
    key = int(phase) % 24
    if key in _bubble_cache:
        return _bubble_cache[key]
    t = key / 24 * 4.0
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x, speed, ph, r, tw in _BUBBLES:
        y = (ph - speed * t) % (H + 40) - 20
        a = int(26 + 50 * (0.5 + 0.5 * math.sin(t * 2 * math.pi / 4 + tw)))
        d.ellipse([x - r, y - r, x + r, y + r], outline=(150, 220, 255, a), width=1)
    _bubble_cache[key] = layer
    return layer


def sprite(name, t=None):
    """角色精灵：原尺寸静态（不做呼吸/浮动/摆动）。"""
    return char(name)


def char_pos(t, spr):
    return 36, H - spr.height - 8


def blink_weight(t):
    phase = t % 4.2
    if phase < 0.08:
        return phase / 0.08
    if phase < 0.22:
        return 1.0
    if phase < 0.32:
        return 1.0 - (phase - 0.22) / 0.10
    return 0.0


def action_at(t):
    tt = t % LOOP
    for a, b, name in ACTIONS:
        if a <= tt < b:
            return name
    return None


def blink_active(t):
    phase = t % 4.2
    return 0.08 <= phase < 0.22


def current_pose(t):
    name = action_at(t)
    if name is None and blink_active(t):
        name = "wink"
    return name or "idle-cute"


def paste_char(img, t, mood=None):
    if mood:
        spr = sprite(mood, t)
        x, y = char_pos(t, spr)
        img.paste(spr, (x, y), spr)
        return

    spr = sprite(current_pose(t), t)
    x, y = char_pos(t, spr)
    img.paste(spr, (x, y), spr)


# ---------------- 时钟 ----------------
_clock_cache = {}


def clock_layer(now, status=None):
    state = (status or {}).get("state", "idle")
    detail = (status or {}).get("detail", "")
    source = (status or {}).get("source", "")
    count = int((status or {}).get("count", 0) or 0)
    key = (now.strftime("%H:%M"), state, detail, source, count)
    if key in _clock_cache:
        return _clock_cache[key]

    layer = Image.new("RGBA", (460, 268), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, 459, 267], radius=26, fill=(8, 14, 28, 150),
                        outline=(90, 180, 235, 90), width=2)

    hhmm = now.strftime("%H:%M")
    date_txt = "%s  %s" % (now.strftime("%Y-%m-%d"), WEEKDAYS[now.weekday()])

    if state == "idle":
        f_time = ImageFont.truetype(FONT_BOLD, 132)
        f_date = ImageFont.truetype(FONT_REG, 26)
        f_cap = ImageFont.truetype(FONT_REG, 20)
        bb = d.textbbox((0, 0), hhmm, font=f_time)
        d.text(((460 - (bb[2] - bb[0])) / 2 - bb[0], 44 - bb[1]), hhmm, font=f_time,
               fill=(240, 247, 255, 255))
        db = d.textbbox((0, 0), date_txt, font=f_date)
        d.text(((460 - (db[2] - db[0])) / 2 - db[0], 196), date_txt, font=f_date,
               fill=(150, 205, 235, 255))
        cap = "待机中 · 鲸鱼娘在看着屏幕"
        cb = d.textbbox((0, 0), cap, font=f_cap)
        d.text(((460 - (cb[2] - cb[0])) / 2 - cb[0], 236), cap, font=f_cap,
               fill=(110, 160, 195, 255))
    else:
        label, color = STATUS_STYLE.get(state, ("● 工作中", (80, 200, 255)))
        f_label = ImageFont.truetype(FONT_BOLD, 58)
        f_detail = ImageFont.truetype(FONT_REG, 24)
        f_time = ImageFont.truetype(FONT_BOLD, 26)
        f_date = ImageFont.truetype(FONT_REG, 20)

        # 状态：最大、最醒目
        lb = d.textbbox((0, 0), label, font=f_label)
        lw = lb[2] - lb[0]
        size = 58
        while lw > 420 and size > 34:
            size -= 2
            f_label = ImageFont.truetype(FONT_BOLD, size)
            lb = d.textbbox((0, 0), label, font=f_label)
            lw = lb[2] - lb[0]
        d.text(((460 - lw) / 2 - lb[0], 30 - lb[1]), label, font=f_label, fill=color + (255,))

        # 细节：一行，居中
        if detail:
            txt = detail if len(detail) <= 20 else detail[:19] + "…"
            tb = d.textbbox((0, 0), txt, font=f_detail)
            d.text(((460 - (tb[2] - tb[0])) / 2 - tb[0], 108), txt, font=f_detail,
                   fill=(165, 200, 225, 255))

        # 分隔线
        d.line([60, 158, 400, 158], fill=(90, 170, 220, 90), width=2)

        # 时间与日期：缩小，放在底部
        tb2 = d.textbbox((0, 0), hhmm, font=f_time)
        db = d.textbbox((0, 0), date_txt, font=f_date)
        group_w = (tb2[2] - tb2[0]) + 14 + (db[2] - db[0])
        x0 = (460 - group_w) / 2
        d.text((x0 - tb2[0], 178 - tb2[1]), hhmm, font=f_time, fill=(190, 220, 240, 255))
        d.text((x0 + (tb2[2] - tb2[0]) + 14 - db[0], 182 - db[1]), date_txt, font=f_date,
               fill=(120, 165, 195, 255))

    if state != "idle" and source:
        label_src = SOURCE_LABELS.get(str(source).lower(), str(source).upper()[:6])
        txt = label_src + ((" +%d" % count) if count else "")
        fb = ImageFont.truetype(FONT_REG, 16)
        tw = d.textlength(txt, font=fb)
        bx1, by0 = 436, 14
        bx0 = bx1 - tw - 16
        d.rounded_rectangle([bx0, by0, bx1, by0 + 26], radius=13,
                            fill=(20, 40, 64, 210), outline=(90, 180, 235, 140), width=1)
        d.text((bx0 + 8, by0 + 4), txt, font=fb, fill=(150, 200, 235, 255))

    _clock_cache.clear()
    _clock_cache[key] = layer
    return layer


def draw_bubble(img, text):
    """竖排气泡：一列优先排满，装不下才开第二列（列从左往右）。"""
    chars = [c for c in str(text) if not c.isspace()]
    if not chars:
        return img
    fs = 25
    pad, col_step = 14, 45
    per_col = 9                      # 一列最多 9 字（受画面高度限制）
    max_chars = per_col * 2
    if len(chars) > max_chars:
        chars = chars[:max_chars - 1] + ["…"]

    cols = [chars[i:i + per_col] for i in range(0, len(chars), per_col)]
    ncols = len(cols)
    x0, y0 = 341, 34
    w = pad * 2 + col_step * ncols
    x1 = x0 + w
    rows = len(cols[0])
    h = rows * (fs + 6) + pad * 2

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x0, y0, x1, y0 + h], radius=18, fill=(10, 18, 34, 235),
                        outline=(110, 200, 245, 230), width=2)
    ty = y0 + min(max(20, h // 2 - 18), h - 44)
    tail = [(x0 + 2, ty), (x0 + 2, ty + 38), (x0 - 34, ty + 10)]
    d.polygon(tail, fill=(10, 18, 34, 235), outline=(110, 200, 245, 230))
    d.rectangle([x0 - 1, ty + 4, x0 + 6, ty + 34], fill=(10, 18, 34, 235))

    f = ImageFont.truetype(FONT_BOLD, fs)
    for ci, col in enumerate(cols):
        cx = x0 + pad + ci * col_step + col_step / 2
        y = y0 + pad
        for ch in col:
            cw = d.textlength(ch, font=f)
            d.text((cx - cw / 2, y), ch, font=f, fill=(236, 246, 255, 255))
            y += fs + 6
    img.paste(layer, (0, 0), layer)
    return img


# ---------------- 画面 ----------------
def idle_frame(t, now, status=None):
    status = status or STATUS
    img = background().copy()
    pose = STATUS_POSE.get(status.get("state"))
    if pose:
        spr = sprite(pose, t)
        x, y = char_pos(t, spr)
        img.paste(spr, (x, y), spr)
    else:
        paste_char(img, t)
    layer = clock_layer(now, status)
    img.paste(layer, (470, 54), layer)
    if bubble_active():
        draw_bubble(img, BUBBLE["text"])
    return img


_card_cache = {}


def text_base(text, sub):
    key = (text, sub)
    if key in _card_cache:
        return _card_cache[key]

    img = background().copy()
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 400, 38, 930, 338
    d.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=(8, 14, 28),
                        outline=(90, 180, 235), width=2)

    max_w = x1 - x0 - 60
    size = 56
    while size > 22:
        f1 = ImageFont.truetype(FONT_BOLD, size)
        if d.textlength(text, font=f1) <= max_w:
            break
        size -= 2
    f1 = ImageFont.truetype(FONT_BOLD, size)
    d.text((x0 + 34, y0 + 40), text, font=f1, fill=(240, 247, 255))

    if sub:
        f2 = ImageFont.truetype(FONT_REG, 24)
        lines, cur = [], ""
        for ch in sub:
            if ch == "\n":
                lines.append(cur)
                cur = ""
            elif d.textlength(cur + ch, font=f2) > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        y = y0 + 40 + size + 24
        for line in lines[:3]:
            d.text((x0 + 34, y), line, font=f2, fill=(140, 200, 235))
            y += 34

    _card_cache.clear()
    _card_cache[key] = img
    return img


def text_frame(text, sub, mood, t):
    img = text_base(text, sub).copy()
    paste_char(img, t, mood=mood)
    return img


def image_frame(path):
    img = Image.open(path).convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left, top = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def encode(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def push_bytes(data):
    with open(TMP, "wb") as fh:
        fh.write(data)
    os.replace(TMP, DATA)

    src_tmp = THEME / ".src.tmp.png"
    try:
        with open(src_tmp, "wb") as fh:
            fh.write(data)
        for attempt in range(4):
            try:
                os.replace(src_tmp, SRC_DATA)
                return
            except OSError:
                time.sleep(0.004)
        # 替换一直失败（软件短暂占用）：退回直写
        with open(SRC_DATA, "wb") as fh:
            fh.write(data)
    except OSError as e:
        log("src write failed: %s" % e)
    finally:
        try:
            if src_tmp.exists():
                src_tmp.unlink()
        except OSError:
            pass


_CMD_LOCK = None


def write_cmd(payload):
    """线程安全地写命令文件：唯一临时名 + 原子替换。"""
    global _CMD_LOCK
    import tempfile
    import threading
    if _CMD_LOCK is None:
        _CMD_LOCK = threading.Lock()
    data = json.dumps(payload, ensure_ascii=False)
    with _CMD_LOCK:
        fd, tmp = tempfile.mkstemp(prefix=".cmd-", suffix=".json", dir=str(CMD.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
            os.replace(tmp, CMD)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def read_cmd():
    try:
        if not CMD.is_file():
            return None
        st = CMD.stat()
        sig = (st.st_mtime_ns, st.st_size)
        if getattr(read_cmd, "last", None) == sig:
            return getattr(read_cmd, "cached", None)
        read_cmd.last = sig
        read_cmd.cached = json.loads(CMD.read_text(encoding="utf-8"))
        return read_cmd.cached
    except Exception as e:
        log("cmd read err: %s" % e)
        return None


def _single_instance():
    """同名互斥量：已经有一份在跑就直接退出。"""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\WhaleGirlPanelDaemon")
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


SOURCE_LABELS = {"dsh": "DSH", "reasonix": "REAX", "hermes": "HERM",
                 "teleagent": "TELE", "manual": "MANUAL", "cmd": "MANUAL"}


def apply_state(stat, now=None):
    """把中枢合成出来的状态落到屏幕上（含气泡规则）。"""
    now = now or time.time()
    prev = (STATUS.get("state"), STATUS.get("detail"))
    new_state = stat.get("state", "idle")
    detail = normalize_detail(new_state, stat.get("detail", ""))
    STATUS["state"] = new_state
    STATUS["detail"] = detail
    STATUS["source"] = stat.get("source", "")
    STATUS["count"] = int(stat.get("count", 0) or 0)
    publish_status()
    if (new_state, detail) == prev:
        return
    log("state -> %s/%s from %s (+%d)"
        % (new_state, detail, STATUS["source"] or "-", STATUS["count"]))
    if new_state in ("approval", "question", "plan"):
        show_bubble(pick_line(new_state), hold=10 ** 9,
                    key=new_state + ":" + detail)
    elif new_state == "working":
        if now - _last_bubble_at["working"] >= WORK_BUBBLE_COOLDOWN:
            show_bubble(pick_line(tool_bucket(detail)), key="work:" + detail)
            _last_bubble_at["working"] = now
    elif new_state == "idle":
        BUBBLE["text"] = ""
        BUBBLE["until"] = 0


def main():
    mutex = _single_instance()
    if mutex is None:
        print("another instance is already running")
        return
    log("daemon start")
    try:
        CMD.unlink()          # 清掉上次遗留的命令，避免重启时被重放
        log("stale cmd cleared")
    except OSError:
        pass
    try:
        import api
        api.start(write_cmd, log, HUB, port=config.port())
    except Exception as e:
        log("api start failed: %s" % e)
    t0 = time.time()
    shown = None
    last_sig = None
    while True:
        start = time.time()
        cmd = read_cmd()
        now = time.time()

        if cmd and getattr(read_cmd, "logged", None) != getattr(read_cmd, "last", None):
            log("cmd: %s" % cmd)
            read_cmd.logged = getattr(read_cmd, "last", None)

        # 同一条命令文件只处理一次：read_cmd 会缓存，否则 resume 每轮重放、
        # 反复 HUB.clear() 会把中枢清空
        cmd_sig = getattr(read_cmd, "last", None)
        if cmd and getattr(main, "cmd_sig", None) != cmd_sig:
            main.cmd_sig = cmd_sig
            if cmd.get("type") == "state":
                try:
                    HUB.report(cmd.get("source") or "manual", cmd.get("state", "idle"),
                               cmd.get("detail", ""), cmd.get("session", ""),
                               cmd.get("ttl"), cmd.get("priority"))
                except ValueError as e:
                    log("bad state report: %s" % e)
            elif cmd.get("type") == "flash":
                sig_now = getattr(read_cmd, "last", None)
                if getattr(main, "flash_sig", None) != sig_now:
                    main.flash_sig = sig_now
                    kind = cmd.get("kind", "success")
                    text = pick_line("flash_" + kind if kind in ("success", "failure") else kind)
                    if text:
                        show_bubble(text, hold=float(cmd.get("seconds", 3) or 3),
                                    key="flash:" + kind)
            elif cmd.get("type") == "resume":
                shown = None
                HUB.clear()
                STATUS["state"] = "idle"
                STATUS["detail"] = ""
                STATUS["source"] = ""
                STATUS["count"] = 0
                publish_status()
                BUBBLE["text"] = ""
                BUBBLE["until"] = 0
            elif cmd.get("type") in ("text", "image"):
                sig = (cmd.get("type"), cmd.get("text"), cmd.get("sub"),
                       cmd.get("mood"), cmd.get("path"))
                if sig != last_sig or shown is None:
                    shown = dict(cmd, sig=sig)
                    last_sig = sig
                else:
                    shown["until"] = cmd.get("until", shown.get("until"))

        best = HUB.compose(now)
        if (best["state"] != STATUS.get("state") or best["detail"] != STATUS.get("detail")
                or best.get("source", "") != STATUS.get("source", "")
                or best.get("count", 0) != STATUS.get("count", 0)):
            apply_state(best, now)

        if shown and now >= shown.get("until", 0):
            shown = None

        # 过期气泡要真正清空，否则后续判断会一直以为“有气泡”
        if BUBBLE["text"] and now >= BUBBLE["until"]:
            BUBBLE["text"] = ""
            BUBBLE["key"] = ""

        # 待机换动作 → 台词跟着换
        global _last_pose, _last_pose_bubble
        if not shown and STATUS.get("state") == "idle":
            pose = current_pose((now - t0) % LOOP)
            if pose != _last_pose:
                _last_pose = pose
                line = pick_line("pose:" + pose)
                if line:
                    show_bubble(line, hold=10.0, key="pose:" + pose)

        if (not shown and STATUS.get("state") == "idle"
                and not BUBBLE["text"] and now - _last_bubble_at["idle"] >= IDLE_CHATTER_GAP):
            show_bubble(pick_line("idle"), key="idle")
            _last_bubble_at["idle"] = now

        t = now - t0
        if shown and shown["type"] == "text":
            sig = ("text", shown.get("text"), shown.get("sub"), shown.get("mood"))
        elif shown and shown["type"] == "image":
            sig = ("image", shown.get("path"))
        else:
            sig = ("idle", STATUS.get("state"), STATUS.get("detail"),
                   STATUS.get("source"), STATUS.get("count"),
                   current_pose(t % LOOP), datetime.now().strftime("%H:%M"),
                   BUBBLE["text"] if bubble_active() else "-")

        if sig == getattr(main, "last_sig", None) and (now - getattr(main, "last_push", 0)) < 5.0:
            time.sleep(0.15)
            continue

        if shown and shown["type"] == "text":
            img = text_frame(shown.get("text", ""), shown.get("sub", ""),
                             shown.get("mood") or "idle-cute", t)
        elif shown and shown["type"] == "image":
            img = image_frame(shown["path"])
        else:
            img = idle_frame(t % LOOP, datetime.now(), STATUS)
        main.last_sig = sig

        data = encode(img)
        last = main.__dict__.get("last_data")
        last_push = main.__dict__.get("last_push", 0.0)
        if data != last or (now - last_push) > 5.0:
            push_bytes(data)
            main.last_data = data
            main.last_push = now
        dt = time.time() - start
        if dt < 1.0 / FPS:
            time.sleep(1.0 / FPS - dt)


if __name__ == "__main__":
    main()








