"""panel_mcp.py — 把鲸鱼娘副屏的 HTTP API 包成 MCP 工具（stdio，纯标准库）。

用法（由 MCP 客户端拉起）：
    python panel_mcp.py

环境变量：
    PANEL_API   默认 http://127.0.0.1:8765

暴露的工具：
    panel_say     显示文字
    panel_state   设置工作状态（working/approval/question/plan/idle）
    panel_flash   瞬时气泡（success/failure）
    panel_resume  回到待机
    panel_health  探活
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

NAME = "jonsbo-panel"
VERSION = "0.1.0"
API = os.environ.get("PANEL_API", "http://127.0.0.1:8765").rstrip("/")
PROTOCOL = "2024-11-05"


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API + path, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(API + path, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


TOOLS = [
    {
        "name": "panel_say",
        "description": "在副屏上显示一段文字，可带副标题和姿态；到期自动回到待机。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "主标题"},
                "sub": {"type": "string", "description": "副标题（可选）"},
                "seconds": {"type": "number", "description": "显示秒数，默认 180；0 表示一直显示"},
                "mood": {"type": "string", "description": "鲸鱼娘姿态（可选，不填自动匹配）"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "panel_state",
        "description": "设置副屏的工作状态：working 工作中 / approval 待审批 / question 等你回答 / plan 计划确认 / idle 待机。状态会一直保持到你下次修改。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["working", "approval", "question", "plan", "idle"],
                },
                "detail": {"type": "string", "description": "卡片上的补充信息，比如工具名或问题摘要"},
            },
            "required": ["state"],
        },
    },
    {
        "name": "panel_flash",
        "description": "弹一个 3 秒的瞬时气泡，不改变当前状态。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["success", "failure"]},
                "seconds": {"type": "number"},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "panel_resume",
        "description": "立即回到待机（时钟 + 角色轮播）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "panel_health",
        "description": "检查副屏服务是否在线。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name: str, args: dict) -> str:
    if name == "panel_say":
        payload = {"text": args.get("text", "")}
        for k in ("sub", "mood"):
            if args.get(k):
                payload[k] = args[k]
        if "seconds" in args:
            payload["seconds"] = args["seconds"]
        return json.dumps(post("/say", payload), ensure_ascii=False)
    if name == "panel_state":
        return json.dumps(post("/state", {
            "state": args.get("state", "idle"),
            "detail": args.get("detail", ""),
        }), ensure_ascii=False)
    if name == "panel_flash":
        payload = {"kind": args.get("kind", "success")}
        if "seconds" in args:
            payload["seconds"] = args["seconds"]
        return json.dumps(post("/flash", payload), ensure_ascii=False)
    if name == "panel_resume":
        return json.dumps(post("/resume", {}), ensure_ascii=False)
    if name == "panel_health":
        return json.dumps(get("/health"), ensure_ascii=False)
    raise ValueError("unknown tool: " + name)


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if mid is None:          # notification：不回
        return None
    if method == "initialize":
        return {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": NAME, "version": VERSION},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            text = call_tool(params.get("name", ""), params.get("arguments") or {})
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except urllib.error.URLError as e:
            return {"content": [{"type": "text", "text": "副屏服务连不上：%s" % e}],
                    "isError": True}
        except Exception as e:  # noqa: BLE001
            return {"content": [{"type": "text", "text": "调用失败：%s" % e}], "isError": True}
    return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = handle(msg)
        if result is None:
            continue
        out = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
