# 04 · DSH 桥接插件

`bridge/dsh-panel-bridge` 是 DeepSeek Harness 的客户端插件：
它不渲染任何东西，只观察页面的 DOM 标记，把「你在忙什么」上报给副屏。

## 它看什么

| DOM 锚点 | 含义 | 上报状态 |
|---|---|---|
| `[data-approval-key]` | 审批弹窗 | `approval` |
| `[data-question-key]` | 提问 | `question` |
| `[data-plan-review-key]` | 计划确认 | `plan` |
| `[data-chat-running]` | 会话运行中 | `working` |
| `[data-tool][data-state="running\|preparing"]` | 工具执行中 | `working` + 工具名 |

优先级：**审批 > 提问 > 计划 > 工作中 > 空闲**。

这些都是 DSH 前端自己写进 DOM 的语义属性，不是本项目伪造的。
DSH 升级若改名，只需同步修改 `lib/client.js` 里的 `computeState()`。

## 成功 / 失败瞬时气泡

插件额外跟踪“工具从运行到结束”：

- 运行中的工具消失 → `POST /flash {kind:"success"}`
- 出现错误标记（`[data-tool][data-state="error"]` / `[data-error]`）→ `POST /flash {kind:"failure"}`

播放器收到后弹 3 秒气泡，不改状态。

## 台词与冷却

台词在 `whale/lines.json`：

```json
{
  "working": ["终端在跑，稍等喵～"],
  "approval": ["这个要你点头哦"],
  "question": ["有个问题要你选～"],
  "poses": { "tail-swing": ["摇摇尾巴～"], "curious": ["嗯？"] },
  "flash_success": ["搞定！"],
  "flash_failure": ["咦，报错了…"]
}
```

播放器侧的节奏（`daemon.py` 顶部常量）：

| 常量 | 默认 | 含义 |
|---|---|---|
| `WORK_BUBBLE_COOLDOWN` | 25s | 工作态气泡冷却 |
| `BUBBLE_HOLD` | 6s | 普通气泡停留 |
| `IDLE_CHATTER_GAP` | 240s | 待机闲聊间隔 |
| `POSE_BUBBLE_GAP` | 30s | 动作台词冷却（当前每换动作必换台词） |

## 安装机制

DSH 的客户端插件必须走模块加载器：

```js
window.__ModuleLoader__.load({
  id: "dsh-panel-bridge",
  factory: (require) => {
    // ...
    exports.apply = apply;
    exports.inject = [];
    return module.exports;
  },
});
```

`package.json` 里声明 `dsh.bundle.patch`（把自己的 id 插进 profile 组合）和
`dsh.client`（浏览器侧入口）。`install_bridge.py` 负责把包放进 profile 的
`plugins/` 与 `node_modules/`，并在 `package.json` 登记。

## 开发与测试

```powershell
cd bridge/dsh-panel-bridge
node test/test-dom.cjs
```

单元测试用假 document 覆盖了：空闲、工具运行、会话运行、审批优先于工具、
提问、计划、审批优先于提问、中文工具名、审批文案清理。

## 已知问题

- **开两个窗口**会各跑一份插件，状态会来回跳。播放器侧已做工具名归一化降低抖动，
  但彻底解决需要只留一个窗口。
- 插件更新后需要重载窗口（`Ctrl+R`）或重启 DSH 才生效。
