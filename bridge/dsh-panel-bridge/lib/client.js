window.__ModuleLoader__.load({
  id: "dsh-panel-bridge",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;

    /**
     * dsh-panel-bridge —— 观察 DSH Web UI 的 DOM 语义标记，把
     * 「工作中 / 待审批 / 待回答 / 计划确认 / 空闲」上报给副屏 API。
     *
     * 只用公开的 data-* 锚点，不改 DSH 任何内置文件、不读业务内容：
     *   [data-chat-running]                会话运行中
     *   [data-tool][data-state=running]    工具在跑（完成后卡片仍留在 DOM，必须看 data-state）
     *   [data-approval-key]                待审批
     *   [data-question-key]                待回答
     *   [data-plan-review-key]             计划待确认
     */
    "use strict";

    var DEFAULT_API = "http://127.0.0.1:8765/report";
    var SOURCE = "dsh";
    var SESSION = "w" + Math.random().toString(36).slice(2, 8);
    var STARTED = false;
    var lastKey = null;
    var debounceTimer = null;

    function apiUrl() {
      try {
        if (typeof localStorage !== "undefined") {
          var v = localStorage.getItem("dsh-panel-bridge:api");
          if (v) return v;
        }
      } catch (e) { /* ignore */ }
      if (typeof window !== "undefined" && window.__DSH_PANEL_API__) return window.__DSH_PANEL_API__;
      return DEFAULT_API;
    }

    function clean(el) {
      if (!el) return "";
      var t = el.innerText || el.textContent || "";
      return String(t).replace(/\s+/g, " ").trim();
    }

    var TOOL_LABELS = {
      pwsh: "终端", bash: "终端", shell: "终端", terminal: "终端",
      read: "读文件", write: "写文件", edit: "改文件", str_replace_editor: "改文件",
      glob: "找文件", grep: "搜内容", ls: "列目录",
      ask_user_question: "提问", web_search: "联网搜索", web_fetch: "读网页",
      subagent: "子任务", subagent_fork: "子任务", workflow: "工作流",
      present: "展示", todo_write: "列计划", skill: "加载技能",
      job_output: "看后台任务", job_kill: "停后台任务", job_list: "看后台任务",
      working_directory: "切换目录", load_workspace_dependencies: "加载依赖",
      schedule_create: "建提醒", schedule_list: "看提醒", create_goal: "定目标",
      update_goal: "更新目标", get_goal: "看目标",
    };

    function toolLabel(name) {
      if (!name) return "";
      return TOOL_LABELS[name] || name;
    }

    /** 审批/提问卡片里取关键信息：去掉前缀、压成一行、截断。 */
    function tidyText(text, limit) {
      var t = String(text || "").replace(/\s+/g, " ").trim();
      t = t.replace(/^等待审批[：:\s]*/, "").replace(/^Approval[：:\s]*/i, "");
      t = t.replace(/[：:，,。\s]+$/, "");
      var max = limit || 22;
      if (t.length > max) t = t.slice(0, max) + "…";
      return t;
    }

    function attr(el, name) {
      if (!el || typeof el.getAttribute !== "function") return "";
      return el.getAttribute(name) || "";
    }

    /** 纯函数：从一个 document 推导当前状态。 */
    function computeState(doc) {
      if (!doc || typeof doc.querySelector !== "function") return { state: "idle", detail: "" };

      // 1) 待审批优先级最高
      var ap = doc.querySelector("[data-approval-key]");
      if (ap) {
        var tool = doc.querySelector('[data-tool][data-state="running"]')
          || doc.querySelector('[data-tool][data-state="preparing"]');
        var detail = tidyText(clean(ap), 22) || toolLabel(attr(tool, "data-tool"));
        return { state: "approval", detail: detail };
      }

      // 2) 待回答 / 计划确认
      var q = doc.querySelector("[data-question-key]");
      if (q) return { state: "question", detail: tidyText(clean(q), 22) };
      var plan = doc.querySelector("[data-plan-review-key]");
      if (plan) return { state: "plan", detail: tidyText(clean(plan), 22) };

      // 3) 工作中
      var tool2 = doc.querySelector('[data-tool][data-state="running"]')
        || doc.querySelector('[data-tool][data-state="preparing"]')
        || doc.querySelector('[data-tool][data-state="ongoing"]');
      var running = doc.querySelector("[data-chat-running]");
      if (running || tool2) {
        return { state: "working", detail: toolLabel(attr(tool2, "data-tool")) };
      }

      // 4) 空闲
      return { state: "idle", detail: "" };
    }

    function post(payload) {
      try {
        if (typeof fetch === "function") {
          var body = {
            source: SOURCE,
            session: SESSION,
            ttl: 30,
            state: payload.state,
            detail: payload.detail,
          };
          fetch(apiUrl(), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            keepalive: true,
          }).catch(function () { /* 副屏没开就算了 */ });
        }
      } catch (e) { /* ignore */ }
    }

    function clearSelf() {
      try {
        if (typeof fetch === "function") {
          fetch(apiUrl().replace(/\/report\/?$/, "/clear"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source: SOURCE, session: SESSION }),
            keepalive: true,
          }).catch(function () {});
        }
      } catch (e) { /* ignore */ }
    }

    var lastErr = 0;
    var lastRun = 0;
    var runSince = 0;

    function postFlash(kind) {
      try {
        var url = apiUrl().replace(/\/state\/?$/, "/flash");
        fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: kind, seconds: 3 }),
          keepalive: true,
        }).catch(function () {});
      } catch (e) { /* ignore */ }
    }

    /** 工具从运行→结束：成功/失败各闪一条 3 秒气泡。 */
    function trackTools(s) {
      if (typeof document === "undefined" || !document.querySelectorAll) return;
      if (s.state === "approval" || s.state === "question") {
        lastErr = document.querySelectorAll('[data-tool][data-state="error"], [data-error]').length;
        return;
      }
      var errCount = document.querySelectorAll('[data-tool][data-state="error"], [data-error]').length;
      var runCount = document.querySelectorAll('[data-tool][data-state="running"], [data-tool][data-state="preparing"]').length;
      var now = Date.now();

      if (runCount > 0 && lastRun === 0) runSince = now;
      if (errCount > lastErr) {
        postFlash("failure");
        runSince = 0;
      } else if (lastRun > 0 && runCount === 0 && runSince && now - runSince > 1500) {
        postFlash("success");
        runSince = 0;
      }
      lastErr = errCount;
      lastRun = runCount;
    }

    var lastPostAt = 0;

    function tick() {
      if (typeof document === "undefined") return;
      var s = computeState(document);
      var key = s.state + "|" + s.detail;
      var now = Date.now();
      // 状态变了立刻发；没变也要每 10 秒续租，否则 DSH 卡住时副屏会自己过期
      if (key !== lastKey || now - lastPostAt > 10000) {
        lastKey = key;
        lastPostAt = now;
        post(s);
      }
      trackTools(s);
    }

    function start() {
      if (STARTED || typeof document === "undefined") return;
      STARTED = true;

      var observe = function () {
        try {
          var target = document.body || document.documentElement;
          if (!target) return;
          var obs = new MutationObserver(function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(tick, 150);
          });
          obs.observe(target, {
            subtree: true,
            childList: true,
            attributes: true,
            attributeFilter: [
              "data-chat-running", "data-state", "data-tool",
              "data-approval-key", "data-question-key", "data-plan-review-key", "aria-busy",
            ],
          });
        } catch (e) { /* ignore */ }
        setInterval(tick, 1000);
        tick();
      };

      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", observe, { once: true });
      } else {
        observe();
      }

      try {
        window.addEventListener("beforeunload", function () {
          clearSelf();
        });
      } catch (e) { /* ignore */ }
    }

    function apply() {
      start();
    }

    exports.apply = apply;
    exports.inject = [];
    // 测试钩子
    exports.computeState = computeState;
    exports.start = start;
    return module.exports;
  },
});

