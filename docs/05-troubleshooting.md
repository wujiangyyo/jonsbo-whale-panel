# 05 · 排障

## 副屏黑屏 / 只有占位图

1. `daemon.py` 是否在跑？`Get-Process pythonw`
2. 接口是否活着？`Invoke-RestMethod http://127.0.0.1:8765/health`
3. 软件当前主题是不是 `WhaleGirl`？（在主题列表里确认）
4. 看 `whale/daemon.log`，最近有没有 `src write failed`

## 主题列表里没有 WhaleGirl

- 跑过 `make_theme.py` 吗？它负责写 `Programme/` 和 `ThemeScheme/<SN>/`
- 写完后**必须重启 JONSBO AIO**
- 若提示 `device SN not found`，先用官方软件连一次屏

## 画面花屏 / 卡帧

- 写 `source/data.png` 时软件可能正在读，读到半张图
- 本项目已改成：根目录用“临时文件 + 原子替换”，source 直写并容错
- 若仍出现，降低 `config.json` 里的 `fps`（如 6）

## 切主题后画面不动了

播放器只往 `WhaleGirl` 的目录写。在软件里点回 `WhaleGirl` 即可恢复；
播放器不需要重启。

## 状态不跟随（一直是待机）

1. 桥接插件装了吗？重启 DSH 了吗？
2. 浏览器控制台有没有 `/state` 请求失败？
3. 两个窗口都开着会互相覆盖——关掉多余窗口
4. 插件更新后要 `Ctrl+R` 重载

## 气泡不换 / 只显示一次

历史 bug：气泡过期后没有清空内部标记，导致后续判断以为“还有气泡”。
当前版本已在过期时清空 `BUBBLE`，并让“换动作换台词”不设冷却。

## 播放器随 DSH 重启一起消失

播放器若由 DSH 进程启动，会作为子进程被杀。改用：
- 启动文件夹里的 `start.bat` 快捷方式（Explorer 拉起）
- 或计划任务

## 端口被占用

改 `whale/config.json` 的 `port`，同时确保插件里的地址一致
（插件默认 `http://127.0.0.1:8765/state`，可在页面 `localStorage` 里设
`dsh-panel-bridge:api` 覆盖）。

## 工作区文件权限被挡（Windows）

如果你在 DSH 的 `workspace-write` 沙箱里运行本项目，可能遇到
`grantWrite(...)` 之类的报错。这是 DSH 沙箱的 ACL 问题，与本项目无关；
把会话切到 full access，或按 DSH 的提示修复工作区权限。

## 日志位置

| 文件 | 内容 |
|---|---|
| `whale/daemon.log` | 状态变化、气泡、接口调用 |
| `whale/cmd.json` | 当前命令（调试用） |
| DSH 控制台 | 插件侧的 `/state` 请求 |
