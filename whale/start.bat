@echo off
rem 无窗口启动鲸鱼娘播放器（JONSBO AIO 需要已经打开并选中 WhaleGirl 主题）
cd /d "%~dp0"
where pythonw >nul 2>&1
if errorlevel 1 (
  echo pythonw not found. Install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)
start "" pythonw "%~dp0daemon.py"
