# 06 · 给其他 Agent 用：MCP 服务器

副屏本身是一个本地 HTTP 服务（`127.0.0.1:8765`），**任何能发请求的程序都能用**，不依赖 DeepSeek Harness。
如果你的 Agent 支持 MCP，用 `bridge/panel-mcp/panel_mcp.py` 会更顺手：它把接口包成 5 个工具，纯标准库、无依赖。

## 工具

| 工具 | 作用 |
|---|---|
| `panel_say` | 显示文字（`text` / `sub` / `seconds` / `mood`） |
| `panel_state` | 设置状态：`working` / `approval` / `question` / `plan` / `idle` |
| `panel_flash` | 瞬时气泡：`success` / `failure` |
| `panel_resume` | 回到待机 |
| `panel_health` | 探活 |

## 前置

1. JONSBO AIO 已打开，且当前主题是 `WhaleGirl`
2. `python whale/daemon.py` 在运行（或 `start.bat`，开机自启）
3. Python 3.10+ 即可，**不需要装任何第三方包**

## 配置示例

### Reasonix

`%AppData%\reasonix\config.toml`（或项目的 `reasonix.toml`）：

```toml
[[plugins]]
name    = "panel"
command = "python"
args    = ["C:/path/to/jonsbo-whale-panel/bridge/panel-mcp/panel_mcp.py"]
```

### Claude Code

```bash
claude mcp add panel -- python C:/path/to/panel_mcp.py
```

### 通用 `.mcp.json`（项目根目录）

```json
{
  "mcpServers": {
    "panel": {
      "command": "python",
      "args": ["C:/path/to/panel_mcp.py"]
    }
  }
}
```

> 注意：Windows 上请用 `python.exe`（不要 `pythonw.exe`，它会吞掉 stdio）。
> 如果客户端环境里 `python` 不在 PATH，直接把 `command` 写成 python 的绝对路径。

## 端口与时序

- 默认连 `http://127.0.0.1:8765`，可用环境变量 `PANEL_API` 覆盖
- 调用是同步 HTTP，超时 5 秒；副屏没开时工具会返回错误文本而不是崩溃
- 状态会一直保持，直到下一次 `panel_state` 或 `panel_resume`

## 不装 MCP 也行

```bash
curl -X POST http://127.0.0.1:8765/state \
  -H "Content-Type: application/json" \
  -d '{"state":"working","detail":"我的 Agent"}'
```

只监听回环地址；跨机使用需要额外加认证与绑定，见 [05-troubleshooting.md](05-troubleshooting.md)。
