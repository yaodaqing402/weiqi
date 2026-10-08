"""棋谱记录：保存、加载、列表、删除，用于回放与管理。"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..engine.board import Board
from ..engine.stones import BLACK, KOMI, Move
from .notation import move_text
from .storage import records_dir

PASS_CODE = [-1, -1]


@dataclass
class GameRecord:
    mode: str = "pve"              # pve / pvp / lan / puzzle
    rule: str = "territory"        # territory 正式对局 / capture 吃子棋
    size: int = 9
    komi: float = KOMI
    capture_target: int = 0        # 吃子棋：先吃够多少子获胜
    black_name: str = "黑方"
    white_name: str = "白方"
    result: Optional[str] = None   # 'b' / 'w' / 'draw' / None(未完成)
    result_detail: str = ""        # 如“3.5 目”“中盘胜”“吃够 5 子”
    difficulty: int = -1
    created: float = 0.0
    setup: List[List] = field(default_factory=list)          # 练习题初始摆子 [[color,r,c], ...]
    moves: List[List[int]] = field(default_factory=list)     # [[r,c], ...]，停一手为 [-1,-1]
    notations: List[str] = field(default_factory=list)

    def add(self, color: str, move: Move, captured: int = 0) -> None:
        self.notations.append(move_text(self.size, color, move, captured))
        self.moves.append(PASS_CODE[:] if move is None else [move[0], move[1]])

    def pop(self) -> None:
        self.moves.pop()
        self.notations.pop()

    def build_start(self) -> Board:
        b = Board(self.size)
        for color, r, c in self.setup:
            b.grid[r][c] = color
        b.turn = BLACK
        return b

    @staticmethod
    def decode(m: List[int]) -> Move:
        return None if list(m) == PASS_CODE else (m[0], m[1])

    @property
    def title(self) -> str:
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.created or time.time()))
        mode_cn = {"pve": "人机", "pvp": "双人", "lan": "联机", "puzzle": "练习"}.get(self.mode, self.mode)
        rule_cn = "吃子棋" if self.rule == "capture" else f"{self.size}路"
        res = {"b": "黑胜", "w": "白胜", "draw": "和棋"}.get(self.result or "", "未完")
        return (f"{t}  [{mode_cn}·{rule_cn}]  {self.black_name} vs {self.white_name}  "
                f"{res}  {len(self.moves)}手")


def _filename(rec: GameRecord) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(rec.created or time.time()))
    return f"game_{ts}.json"


def save_record(rec: GameRecord) -> Path:
    if not rec.created:
        rec.created = time.time()
    path = records_dir() / _filename(rec)
    # 避免同秒重名
    i = 1
    while path.exists():
        path = records_dir() / _filename(rec).replace(".json", f"_{i}.json")
        i += 1
    path.write_text(json.dumps(asdict(rec), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_record(path: Path) -> Optional[GameRecord]:
    try:
        data: Dict = json.loads(Path(path).read_text(encoding="utf-8"))
        return GameRecord(**data)
    except (ValueError, OSError, TypeError):
        return None


def list_records() -> List[tuple]:
    """返回 [(path, GameRecord), ...]，按时间倒序。"""
    out = []
    for p in records_dir().glob("*.json"):
        rec = load_record(p)
        if rec is not None:
            out.append((p, rec))
    out.sort(key=lambda x: x[1].created, reverse=True)
    return out


def delete_record(path: Path) -> bool:
    try:
        Path(path).unlink()
        return True
    except OSError:
        return False
