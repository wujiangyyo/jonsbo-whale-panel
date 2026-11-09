#!/usr/bin/env node
/**
 * panel-hook.js — 把 Reasonix 的 hook 事件推成鲸鱼娘副屏状态。
 *
 * 事件 payload 是一行 JSON（从 stdin 读），由 Reasonix hooks 拉起：
 *   node panel-hook.js prompt    # UserPromptSubmit -> 清掉上一轮，推 ● 工作中
 *   node panel-hook.js working   # PreToolUse      -> ● 工作中（detail = 工具名）
 *   node panel-hook.js notify    # Notification    -> ● 待审批 / 等你回答
 *   node panel-hook.js idle      # Stop            -> 清掉本 hook 的状态，回待机
 *
 * 设计要点：
 *  - 副屏没开 / 超时：静默退出，永远 exit 0，绝不阻塞 Reasonix。
 *  - 面板自身的调用（toolName 含 panel_）一律不推送，交给 MCP 自己管。
 *  - 状态优先级由 daemon 的 hub.py 裁决（approval 100 > question 90 >
 *    plan 70 > working 40 > idle 10）。
 *  - 本 hook 用 source=reasonix、session=hook，与 MCP 的 reasonix/- 分开记账。
 *  - 审批/提问结束后，先清掉 session=hook 的记录再报新状态，避免 100 优先级卡住。
 */
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

const action = process.argv[2] || "working";
const PORT = Number(process.env.PANEL_PORT || 8765);
const SOURCE = process.env.PANEL_SOURCE || "reasonix";
const SESSION = "hook";

const HOOK_DIR = path.join(os.homedir(), ".reasonix", "hooks");
const LOG_FILE = path.join(HOOK_DIR, "panel-hook.log");

function logline(msg) {
  try {
    fs.mkdirSync(HOOK_DIR, { recursive: true });
    try {
      if (fs.statSync(LOG_FILE).size > 64 * 1024) fs.writeFileSync(LOG_FILE, "", "utf8");
    } catch {
      /* first write */
    }
    fs.appendFileSync(LOG_FILE, new Date().toISOString() + " " + msg + "\n", "utf8");
  } catch {
    /* logging must never break the hook */
  }
}

/** POST 到副屏；done 为空表示这是最后一个请求，结束后退出。 */
function send(endpoint, payload, done) {
  logline("POST " + endpoint + " " + JSON.stringify(payload));
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  const req = http.request(
    {
      host: "127.0.0.1",
      port: PORT,
      path: endpoint,
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": body.length,
      },
      timeout: 1500,
    },
    (res) => {
      let out = "";
      res.setEncoding("utf8");
      res.on("data", (c) => (out += c));
      res.on("end", () => {
        logline("RES " + endpoint + " " + res.statusCode + " " + out.slice(0, 160));
        done ? done() : process.exit(0);
      });
    }
  );
  req.on("error", (e) => {
    logline("ERR " + endpoint + " " + e.code + " " + e.message);
    process.exit(0); // 副屏没开也不能挡住 Reasonix
  });
  req.on("timeout", () => {
    logline("TIMEOUT " + endpoint);
    req.destroy();
    process.exit(0);
  });
  req.end(body);
}

function reportState(state, detail, ttl) {
  const payload = { state, detail, source: SOURCE, session: SESSION };
  if (ttl) payload.ttl = ttl;
  send("/report", payload);
}

/** 先清掉本 hook 的旧记录，再报新状态（避免 approval 的 100 优先级卡住）。 */
function replaceState(state, detail, ttl) {
  send("/clear", { source: SOURCE, session: SESSION }, () => reportState(state, detail, ttl));
}

/** 从 Notification 的 message 里判类型并提取 detail。 */
function parseNotification(message) {
  const raw = String(message || "").trim();
  const lower = raw.toLowerCase();
  // 计划确认优先于普通审批：消息里同时提到"计划/plan"和"批准/确认"时归为 plan
  const isPlan = /plan|计划/.test(lower);
  const isApproval = /approv|permission|审批|授权|批准|确认/.test(lower);
  // 提问类：Question / 需要回答 / 需要你决定 / 请选择 …
  const isQuestion = /question|ask_?user|input required|回答|提问|请输入|请选择|决定|需要你/.test(lower);
  if (isPlan && (isApproval || /确认|review/.test(lower))) {
    let d = raw.replace(/^[^:：]*[:：]\s*/, "").trim() || "计划待确认";
    if (d.length > 40) d = d.slice(0, 39) + "…";
    return { state: "plan", detail: d };
  }
  if (!isApproval && !isQuestion) return null;

  // "approval needed: bash go test ./..." -> "bash go test ./..."
  let detail = raw.replace(/^[^:：]*[:：]\s*/, "").trim();
  if (!detail) detail = isApproval ? "等待你批准" : "等待你回答";
  if (detail.length > 40) detail = detail.slice(0, 39) + "…";
  return { state: isApproval ? "approval" : "question", detail };
}

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (raw += d));
process.stdin.on("end", () => {
  let payload = {};
  try {
    payload = JSON.parse(raw.trim() || "{}");
  } catch {
    payload = {};
  }

  const tool = String(payload.toolName || payload.tool_name || "").trim();
  logline("event action=" + action + " tool=" + (tool || "-") +
          (payload.message ? " msg=" + String(payload.message).slice(0, 120) : ""));

  // 面板自己的调用不改变屏幕状态
  if (tool.includes("panel_")) process.exit(0);

  if (action === "idle") {
    replaceState("idle", "");
    return;
  }

  if (action === "prompt") {
    replaceState("working", "");
    return;
  }

  if (action === "notify") {
    const hit = parseNotification(payload.message);
    if (!hit) process.exit(0);
    replaceState(hit.state, hit.detail, 120);
    return;
  }

  // PreToolUse：工具已获准执行，说明审批结束，先清再报新状态。
  // 结构化优先：ask 类工具（问用户）直接判为 question，不猜文案。
  const ASK_TOOL = /(^|_)(ask|question|request_user_input|elicit)/i;
  if (ASK_TOOL.test(tool)) {
    const args = payload.toolArgs || {};
    const q = String(args.question || args.message || args.prompt || args.text || "").trim();
    const detail = q ? (q.length > 40 ? q.slice(0, 39) + "…" : q) : "等待你回答";
    replaceState("question", detail, 120);
    return;
  }
  replaceState("working", tool || "");
});
