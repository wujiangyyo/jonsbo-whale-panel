// test-dom.cjs — 以 __ModuleLoader__ 方式加载 client.js，验证状态优先级与文案处理
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const code = fs.readFileSync(path.join(__dirname, "..", "lib", "client.js"), "utf8");
let def = null;
const fakeWindow = { __ModuleLoader__: { load: (d) => { def = d; } } };
new Function("window", code)(fakeWindow);
assert.ok(def, "module loader should be called");
const mod = def.factory(() => ({}));
const computeState = mod.computeState;
assert.strictEqual(typeof computeState, "function", "computeState exported");

function el(text, attrName, attrVal) {
  return {
    innerText: text || "",
    getAttribute: (n) => (n === attrName ? attrVal : null),
  };
}
function doc(map) {
  return { querySelector: (sel) => (sel in map ? map[sel] : null) };
}

const cases = [
  ["空闲", doc({}), "idle", ""],
  ["工具运行中（中文标签）", doc({ '[data-tool][data-state="running"]': el("", "data-tool", "pwsh") }), "working", "终端"],
  ["未知工具原样显示", doc({ '[data-tool][data-state="running"]': el("", "data-tool", "foo") }), "working", "foo"],
  ["会话运行中", doc({ "[data-chat-running]": el("") }), "working", ""],
  ["待审批优先于工具", doc({
    "[data-approval-key]": el("需要写权限"),
    '[data-tool][data-state="running"]': el("", "data-tool", "pwsh"),
  }), "approval", "需要写权限"],
  ["审批文案去前缀并截断", doc({
    "[data-approval-key]": el("等待审批 允许本次操作使用 danger-full-access 权限："),
  }), "approval", "允许本次操作使用 danger-full-a…"],
  ["待回答", doc({ "[data-question-key]": el("要用哪种方案？") }), "question", "要用哪种方案？"],
  ["计划确认", doc({ "[data-plan-review-key]": el("计划待确认") }), "plan", "计划待确认"],
  ["审批优先于提问", doc({
    "[data-approval-key]": el("允许执行？"),
    "[data-question-key]": el("选一个"),
  }), "approval", "允许执行？"],
];

let failed = 0;
for (const [name, d, wantState, wantDetail] of cases) {
  const got = computeState(d);
  try {
    assert.strictEqual(got.state, wantState);
    assert.strictEqual(got.detail, wantDetail);
    console.log("PASS", name, "->", got.state, JSON.stringify(got.detail));
  } catch (e) {
    failed++;
    console.log("FAIL", name, "->", JSON.stringify(got), "expected", wantState, wantDetail);
  }
}
console.log(failed === 0 ? "ALL PASS" : failed + " FAILED");
process.exit(failed === 0 ? 0 : 1);

