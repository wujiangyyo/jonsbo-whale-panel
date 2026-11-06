# 02 · 安装与配置

## 0. 环境要求

| 项 | 要求 |
|---|---|
| 系统 | Windows 10/11（JONSBO AIO 只有 Windows 版） |
| JONSBO AIO | 已安装、能正常显示任意主题 |
| Python | 3.10+，装好 `pillow` |
| 立绘素材 | 安装 `dsh-whale-musume`（DSH 插件），或手改 `config.json` 里的 `assets_dir` |

```powershell
pip install pillow
```

## 1. 创建并注册主题

```powershell
cd whale
python make_theme.py
```

脚本会：

1. 在 `%LOCALAPPDATA%\JONSBO-AIO\Programme\WhaleGirl\` 生成主题文件
2. 在 `%LOCALAPPDATA%\JONSBO-AIO\ThemeScheme\<设备SN>\WhaleGirl.json` 注册
3. 打印设备 SN 与下一步提示

然后**重启 JONSBO AIO**，在主题列表里选 `WhaleGirl`。
此时屏幕会是一张“主题已就绪”的占位图——正常，播放器还没启动。

> 若提示 `device SN not found`：软件还没连过屏，先用官方软件连一次再跑。

## 2. 启动播放器

```powershell
python daemon.py
```

或双击 `start.bat`（`pythonw` 无窗口）。

启动后副屏应出现：左侧鲸鱼娘 + 右侧时钟，每 5–8 秒换一个姿态并冒一句台词。

### 开机自启（可选）

把 `start.bat` 的快捷方式放进：

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

注意：**不要**用命令行把播放器挂在 DeepSeek Harness 下面启动，否则 DSH 重启会把它一起杀掉。
用快捷方式（由 Explorer 拉起）或计划任务。

## 3. 安装 DSH 桥接插件（可选）

想让副屏自动跟随真实状态，才需要这步。

```powershell
cd bridge
python install_bridge.py
```

脚本会：

- 复制插件到 `%USERPROFILE%\.dsh\profiles\desktop\plugins\dsh-panel-bridge`
- 同步一份到 `node_modules`（供模块解析）
- 在 profile 的 `package.json` 里登记依赖与 bundle（原文件备份为 `package.json.before-bridge`）

然后**重启 DeepSeek Harness**。

卸载：

```powershell
python uninstall_bridge.py
```

## 4. 配置文件（可选）

`whale/config.json`（首次运行可不建，全部有默认值）：

```json
{
  "jonsbo_dir": "",
  "theme_name": "WhaleGirl",
  "assets_dir": "",
  "port": 8765,
  "fps": 10,
  "font_bold": "",
  "font_regular": ""
}
```

| 字段 | 默认行为 |
|---|---|
| `jonsbo_dir` | 空 = `%LOCALAPPDATA%\JONSBO-AIO` |
| `theme_name` | 主题名，同时决定目录名 |
| `assets_dir` | 空 = 自动在 `%USERPROFILE%\.dsh\profiles\*\node_modules\dsh-whale-musume\assets\generated` 里找 |
| `port` | 本地 HTTP 端口 |
| `fps` | 渲染帧率（10 足够；调高会加 CPU） |
| `font_bold/regular` | 空 = 微软雅黑，找不到时回落黑体 |

## 5. 验证安装

```powershell
# 1) 接口是否活着
Invoke-RestMethod http://127.0.0.1:8765/health

# 2) 推一个状态看看
Invoke-RestMethod -Uri http://127.0.0.1:8765/state -Method Post `
  -ContentType 'application/json' -Body '{"state":"working","detail":"终端"}'

# 3) 恢复待机
Invoke-RestMethod -Uri http://127.0.0.1:8765/state -Method Post `
  -ContentType 'application/json' -Body '{"state":"idle"}'
```
