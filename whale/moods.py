"""moods.py — 文字内容 → 鲸鱼娘姿态。"""

MOODS = [
    (("开会", "会议", "评审", "meeting"), "work-meeting"),
    (("吃饭", "午餐", "晚餐", "宵夜", "咖啡", "coffee", "奶茶"), "eat"),
    (("完成", "搞定", "成功", "通过", "上线", "deploy", "done", "ok"), "success"),
    (("失败", "报错", "错误", "bug", "崩溃", "挂了"), "failure"),
    (("睡", "晚安", "休息", "困", "摸鱼"), "sleep"),
    (("喜欢", "爱你", "想你", "心动"), "meme-heart"),
    (("谢谢", "厉害", "棒", "好看"), "blush"),
    (("你好", "在吗", "hi", "hello", "早"), "greet"),
    (("加班", "赶工", "deadline"), "work-deadline"),
    (("等", "稍", "马上", "稍后"), "thinking"),
    (("为什么", "怎么", "?", "？"), "curious"),
]


def pick_mood(text: str) -> str:
    low = (text or "").lower()
    for words, mood in MOODS:
        for w in words:
            if w.lower() in low:
                return mood
    return "idle-cute"
