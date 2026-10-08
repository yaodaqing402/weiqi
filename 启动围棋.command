#!/bin/bash
# macOS 双击启动脚本：自动创建虚拟环境、安装依赖并运行游戏。
cd "$(dirname "$0")" || exit 1

PY=python3
if ! command -v $PY >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.10+"; read -r _; exit 1
fi

if [ ! -d ".venv" ]; then
  echo "首次运行：正在创建虚拟环境并安装依赖…"
  $PY -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi

PYTHONPATH=src ./.venv/bin/python -m weiqi
