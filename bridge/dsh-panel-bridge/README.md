# dsh-panel-bridge

把 DeepSeek Harness 的**工作 / 待审批 / 待回答 / 计划确认**状态实时同步到鲸鱼娘副屏。

## 原理

浏览器侧插件，观察 DSH Web UI 的 DOM 语义标记（只读，不改任何内置文件）：

| DOM 锚点 | 含义 |
|---|---|
| `[data-approval-key]` | 有一个待审批的请求 |
| `[data-question-key]` | 有一个待回答的问题 |
| `[data-plan-review-key]` | 计划待确认 |
| `[data-chat-running]` | 会话正在运行 |
| `[data-tool][data-state="running\|preparing"]` | 工具正在执行 |

优先级：**审批 > 提问 > 计划 > 工作中 > 空闲**。
状态变化时 `POST http://127.0.0.1:8765/state`，副屏切换姿态与状态条。

## 安装

```powershell
python install_bridge.py     # 复制文件 + 登记到 profile
```

然后**重启 DeepSeek Harness**（客户端插件在启动时加载）。

回退：

```powershell
python uninstall_bridge.py   # 删除副本 + 还原 package.json
```

## 验证

```powershell
# 手动模拟一次状态上报
Invoke-RestMethod -Uri http://127.0.0.1:8765/state -Method Post `
  -ContentType 'application/json' -Body '{"state":"approval","detail":"写文件权限"}'

# 恢复正常
Invoke-RestMethod -Uri http://127.0.0.1:8765/state -Method Post `
  -ContentType 'application/json' -Body '{"state":"idle"}'
```

## 状态与画面

| state | 姿态 | 卡片 |
|---|---|---|
| `idle` | 18 姿态轮播 | 时钟 + “待机中” |
| `working` | 抱笔记本（running） | `● 工作中` + 工具名 |
| `approval` | 待命（waiting） | `● 待审批`（红） |
| `question` | 好奇（curious） | `● 等你回答`（黄） |
| `plan` | 思考（thinking） | `● 计划待确认`（紫） |

## 兼容性

依赖 DSH 的客户端 DOM 契约（`data-approval-key` 等），DSH 升级后若标记改名需要同步修改
`lib/client.js` 的 `computeState()`。单元测试：

```powershell
node test/test-dom.cjs
```
