# 03 · HTTP API

本地接口，默认监听 `http://127.0.0.1:8765`（端口可在 `whale/config.json` 改）。
只对本机开放，无鉴权；已允许跨源，方便浏览器 / DSH 插件直接调用。

## 端点总览

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/say` | 显示文字（到期自动回待机） |
| POST | `/image` | 显示图片 |
| POST | `/state` | 设置工作状态（工作中/待审批/待回答/计划） |
| POST | `/flash` | 瞬时气泡（成功/失败，默认 3 秒） |
| POST | `/resume` | 立刻回到待机 |
| GET | `/health` | 探活 |
| GET | `/state` | 查询合成后的真实状态（含所有活跃源） |
| POST | `/report` | 多 Agent 上报（带 source/session/ttl） |
| POST | `/clear` | 清除某个源 |

## POST /say

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 主标题 |
| `sub` | string | 否 | 副标题 |
| `mood` | string | 否 | 鲸鱼娘姿态，不填按关键词自动匹配 |
| `seconds` | number | 否 | 显示时长，默认 180；`0` = 一直显示到 `/resume` |

```json
{"ok": true, "applied": {"type": "text", "text": "开会中", "sub": "14:00-15:00",
                         "mood": "work-meeting", "until": 1793785928.63}}
```

## POST /image

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | 是 | 图片绝对路径（PNG/JPG） |
| `seconds` | number | 否 | 默认 30；`0` = 一直显示 |

图片按比例裁切铺满 960×376。

## POST /state

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `state` | string | 是 | `working` / `approval` / `question` / `plan` / `idle` |
| `detail` | string | 否 | 显示在卡片上的补充（工具名、问题摘要…） |

状态会**一直保持**，直到下一次 `/state` 或 `/resume`。

| state | 姿态 | 卡片 |
|---|---|---|
| `idle` | 姿态轮播 | 时钟 + “待机中” |
| `working` | 抱笔记本 | `● 工作中` + 工具名 |
| `approval` | 待命 | `● 待审批`（红） |
| `question` | 好奇 | `● 等你回答`（黄） |
| `plan` | 思考 | `● 计划待确认`（紫） |

## POST /report（多 Agent 推荐）

多个 Agent 共用一块屏时用这个：每个上报者一条记录，按优先级合成。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `source` | string | 是 | Agent 标识：`dsh` / `reasonix` / `hermes` / `teleagent`… |
| `session` | string | 否 | 区分同一 Agent 的多个会话 |
| `state` | string | 是 | `working` / `approval` / `question` / `plan` / `done` / `idle` |
| `detail` | string | 否 | 卡片上的补充信息 |
| `ttl` | number | 否 | 过期秒数；不填按状态给默认值 |
| `priority` | number | 否 | 覆盖默认优先级 |

默认优先级：`approval 100 > question 90 > plan 70 > working 40 > done 30 > idle 10`，
同优先级取最近更新。屏幕显示最高优先级的那个源，角落标 `来源 +N`。

```json
{"source":"reasonix","state":"approval","detail":"要执行 git push","ttl":300}
```

## POST /clear

Agent 退出时清掉自己的状态，避免僵尸：

```json
{"source":"reasonix"}
```

## GET /state

返回副屏**真实**状态（不是最近一次请求）。`cmd.json` 可能停在一条被忽略的请求上，排查时看这里。

```json
{"state": "approval", "detail": "要执行 git push",
 "sticky_until": 1794193801.8, "ts": 1794193621.9}
```

## 粘性状态

`approval` / `question` / `plan` 是**粘性**的：默认 180 秒内不会被自动的 `working` / `idle` 覆盖，
避免「Reasonix 设了待审批，DSH 桥接插件一跑命令就盖成工作中」。

想立刻覆盖，带 `force`：

```json
{"state": "idle", "force": true}
```

`/resume` 永远无条件生效。

## POST /flash

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `kind` | string | 是 | `success` / `failure` |
| `seconds` | number | 否 | 默认 3 |

只弹一句气泡，不改状态，到期自动消失。

## POST /resume / GET /health

```json
{"ok": true, "applied": {"type": "resume"}}
{"ok": true, "ts": 1793785868.61}
```

## 错误

| 状态码 | 场景 |
|---|---|
| 400 | JSON 非法、缺 `text`/`path`、未知 `state`/`kind` |
| 404 | 未知路径 |
| 连接被拒 | 播放器没在跑 |

## 调用示例

```powershell
# 文字
Invoke-RestMethod -Uri http://127.0.0.1:8765/say -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body (@{ text = "开会中"; sub = "14:00-15:00"; seconds = 600 } | ConvertTo-Json)

# 状态
Invoke-RestMethod -Uri http://127.0.0.1:8765/state -Method Post `
  -ContentType 'application/json' -Body '{"state":"working","detail":"终端"}'

# 瞬时气泡
Invoke-RestMethod -Uri http://127.0.0.1:8765/flash -Method Post `
  -ContentType 'application/json' -Body '{"kind":"success"}'
```

```bash
curl -X POST http://127.0.0.1:8765/say \
  -H "Content-Type: application/json" \
  -d '{"text":"构建失败","sub":"看下 CI 日志","seconds":120}'
```

```python
import requests
requests.post("http://127.0.0.1:8765/say",
              json={"text": "下载完成", "sub": "共 128 个文件", "seconds": 30})
```

## 姿态（mood）自动匹配

`/say` 不传 `mood` 时按关键词匹配：

| 关键词 | mood |
|---|---|
| 开会 / 会议 / 评审 / meeting | `work-meeting` |
| 吃饭 / 午餐 / 咖啡 / 奶茶 | `eat` |
| 完成 / 搞定 / 成功 / 上线 / done | `success` |
| 失败 / 报错 / bug / 崩溃 | `failure` |
| 睡 / 晚安 / 休息 / 摸鱼 | `sleep` |
| 喜欢 / 爱你 / 心动 | `meme-heart` |
| 谢谢 / 厉害 / 棒 | `blush` |
| 你好 / 在吗 / 早 | `greet` |
| 加班 / 赶工 / deadline | `work-deadline` |
| 等 / 稍 / 马上 | `thinking` |
| 为什么 / 怎么 / ? | `curious` |

也可以直接传素材里的姿态名，例如 `work-debug`、`work-idea`、`daily-coffee`、
`daily-stretch`、`daily-gaming`、`meme-peace`、`meme-smug`、`weather-umbrella`、
`star`、`pick-up`、`celebrate`、`tail-swing`、`wink`。
