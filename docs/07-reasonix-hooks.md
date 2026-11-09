# 07 · Reasonix 接入（hooks + MCP）

Reasonix 有完整的 hooks 事件，能做到**确定性**的状态上报，不依赖模型自觉。

## 为什么只靠 MCP 不够

实际测试：模型会把所有动作都报成 `working`（连"正在等你确认"也只写进 `detail`），
从来不会主动发 `approval` / `question`。所以需要 hooks 在宿主事件点触发。

## 推荐组合

| 事件 | 动作 | 映射 |
|---|---|---|
| `UserPromptSubmit` | `prompt` | 清上一轮 → `working` |
| `PreToolUse` | `working` | 工具已获准执行 → 清审批 → `working` |
| `Notification` | `notify` | 等待审批 / 等待回答 → `approval` / `question` |
| `Stop` | `idle` | 清本会话状态 → 待机 |

`Notification` 是审批的关键：Reasonix 在需要用户注意时（例如等待工具审批）触发它，
payload 里带 `message`，形如 `approval needed: bash git push origin main`。

## 安装

1. 把 `panel-hook.js` 放到 `%USERPROFILE%\.reasonix\hooks\panel-hook.js`
2. 在 `<Reasonix home>/settings.json` 里注册 hooks：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "command": "\"C:\\tools\\nodejs\\node.exe\" \"C:\\Users\\你\\.reasonix\\hooks\\panel-hook.js\" prompt", "timeout": 3000 }
    ],
    "PreToolUse": [
      { "match": "*", "command": "\"C:\\tools\\nodejs\\node.exe\" \"C:\\Users\\你\\.reasonix\\hooks\\panel-hook.js\" working", "timeout": 3000 }
    ],
    "Notification": [
      { "command": "\"C:\\tools\\nodejs\\node.exe\" \"C:\\Users\\你\\.reasonix\\hooks\\panel-hook.js\" notify", "timeout": 3000 }
    ],
    "Stop": [
      { "match": "*", "command": "\"C:\\tools\\nodejs\\node.exe\" \"C:\\Users\\你\\.reasonix\\hooks\\panel-hook.js\" idle", "timeout": 3000 }
    ]
  }
}
```

3. **重启 Reasonix**（hooks 在会话构建时加载，`/new` 不会重新读配置）

## 同时挂 MCP

`panel-hook.js` 用 `source=reasonix, session=hook` 记账；MCP 用 `source=reasonix, session=-`，
两者互不覆盖。MCP 的 `panel_state` 给模型做"显式声明"（比如它想主动说"这一步需要你确认"），
hooks 负责兜底。

## 排障

- 看 `%USERPROFILE%\.reasonix\hooks\panel-hook.log`，每次 POST 和响应都在里面
- hook 永远 `exit 0`，副屏没开也不会阻塞 Reasonix
- 审批卡住不消失：`PreToolUse` 会先清掉 `session=hook` 再报 `working`，
  所以放行后会立刻切走；如果真的卡了，用 `panel.py clear --source reasonix` 手动清
