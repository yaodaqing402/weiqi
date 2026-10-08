@echo off
REM Windows 双击启动脚本：自动创建虚拟环境、安装依赖并运行游戏。
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 python，请先安装 Python 3.10+ 并勾选 Add to PATH
  pause
  exit /b 1
)

if not exist ".venv" (
  echo 首次运行：正在创建虚拟环境并安装依赖...
  python -m venv .venv
  .venv\Scripts\pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)

set PYTHONPATH=src
.venv\Scripts\python -m weiqi
pause
