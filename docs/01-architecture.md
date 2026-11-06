# 01 · 架构与原理

## 一句话

**JONSBO AIO 是渲染器，自定义主题是画布，`daemon.py` 是画笔，DSH 插件是遥控器。**

## 1. 为什么可以这样玩

JONSBO AIO 加载一个主题时，会把主题目录当作资源根：

```
%LOCALAPPDATA%\JONSBO-AIO\Programme\<主题名>\
├─ Setting.txt        # 图层定义（name/width/height + 每层的位置与 z）
├─ <主题名>.json      # 主题元数据（尺寸、背景、是否触屏…）
├─ data.png           # 图片层
├─ back.png           # 背景
├─ demo.png           # 主题列表缩略图
└─ source\            # 资源副本
```

两个实测出来的关键行为：

1. **图片资源是逐帧重读的**：换掉 `data.png` / `source\data.png`，画面立刻变，不用重启软件。
2. **`source\` 里的副本才是软件真正读取的那份**；根目录的 `data.png` 更像“变更信号”。
   所以写图时要**两份都写**，并且根目录用原子替换（临时文件 + rename），
   否则软件可能读到半张图，表现为花屏/卡帧。

文字、图层结构（`Setting.txt`）则只在“应用主题”那一刻读一次——这也是为什么我们
不去改别人主题的文字，而是自建一个纯图片层的主题 `WhaleGirl`。

## 2. 主题长什么样

`Setting.txt` 极简，只有一行图片层：

```
name:WhaleGirl
width:960
height:376
data.png:x@0,y@0,z@-1
```

`z@-1` 表示最底层；因为没有其它图层，它实际就是整幅画面。
`make_theme.py` 会同时把主题注册进 `ThemeScheme\<设备SN>\`，软件启动时才知道“已安装”。

## 3. 播放器做了什么

`whale/daemon.py` 是一个 10fps 的渲染循环：

```
读 cmd.json（命令） → 决定当前状态 → 画 960×376 的 PNG → 写两份文件
```

画面由三部分组成：

- **角色层**：从 `dsh-whale-musume` 的立绘里取一张（透明背景），按状态/动作选图
- **信息层**：右侧卡片（待机=时钟；工作中/待审批/待回答=大号状态字 + 小时间）
- **气泡层**：竖排台词，一列最多 9 字，超出接第二列（从左往右）

只有“画面真的变了”才重新编码写盘（状态签名比对），静态时 CPU ≈ 1%。

## 4. 状态从哪来

### 手动

`say.py` / HTTP 接口 → 写 `cmd.json` → 播放器读取。

### 自动（DSH）

`bridge/dsh-panel-bridge` 是 DeepSeek Harness 的**客户端插件**，跑在 Web UI 里，
只读 DOM 上的语义标记，变化时 `POST http://127.0.0.1:8765/state`：

| DOM 锚点 | 含义 |
|---|---|
| `[data-approval-key]` | 待审批 |
| `[data-question-key]` | 待回答 |
| `[data-plan-review-key]` | 计划待确认 |
| `[data-chat-running]` | 会话运行中 |
| `[data-tool][data-state="running"]` | 工具执行中（`data-tool` 的值就是工具名） |

优先级：**审批 > 提问 > 计划 > 工作中 > 空闲**。

## 5. 数据流总览

```
DSH 页面 DOM ──(插件 MutationObserver)──▶ POST /state
                                              │
say.py ──(HTTP)───────────────────────────────┤
                                              ▼
                                         cmd.json
                                              │ 每 100ms 读
                                              ▼
                                        daemon.py 渲染
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                     data.png（原子替换）            source/data.png（直写）
                              └───────────────┬───────────────┘
                                              ▼
                                    JONSBO AIO 逐帧读取
                                              │ USB
                                              ▼
                                          DS339 屏幕
```

## 6. 已知边界

- 换主题（在软件里点别的主题）会让画面回到那个主题，播放器继续写文件但不会自动切回来。
- 播放器必须由“非 DSH 子进程”的方式启动（快捷方式 / 计划任务），否则 DSH 重启会把它带走。
- 软件的版本更新可能改动资源读取方式，届时需要重新验证。
