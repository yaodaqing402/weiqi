"""用户数据目录与设置读写（跨平台）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

APP_NAME = "WeiQi"


def data_dir() -> Path:
    override = os.environ.get("WEIQI_DATA_DIR")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def records_dir() -> Path:
    d = data_dir() / "records"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _settings_path() -> Path:
    return data_dir() / "settings.json"


DEFAULT_SETTINGS: Dict[str, Any] = {
    "player_name": "小棋手",
    "sound": True,
    "difficulty": 1,
    "rank_score": 0,
    "wins": 0,
    "losses": 0,
    "draws": 0,
    # 上次对局选项
    "rule": "capture",          # capture 吃子棋 / territory 正式对局
    "board_size": 9,
    "capture_target": 3,
    # KataGo 引擎（留空则自动查找）
    "use_katago": True,
    "katago_path": "",
    "katago_model": "",
    "katago_human_model": "",
}


def load_settings() -> Dict[str, Any]:
    path = _settings_path()
    data = dict(DEFAULT_SETTINGS)
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return data


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        _settings_path().write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
