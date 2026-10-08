"""着法记谱：坐标采用国际通行写法（列字母跳过 I + 行号，左下角为 A1），如“黑 D4”“白 停一手”。"""
from __future__ import annotations

from typing import Optional

from ..engine.stones import BLACK, COL_LETTERS, Move


def coord(size: int, move: Move) -> str:
    if move is None:
        return "停一手"
    r, c = move
    return f"{COL_LETTERS[c]}{size - r}"


def move_text(size: int, color: str, move: Move, captured: int = 0) -> str:
    who = "黑" if color == BLACK else "白"
    s = f"{who} {coord(size, move)}"
    if captured:
        s += f" 提{captured}"
    return s


def result_text(winner: Optional[str], detail: str = "") -> str:
    if winner is None:
        return "对局进行中"
    if winner == "draw":
        return "和棋"
    base = "黑胜" if winner == BLACK else "白胜"
    return f"{base} {detail}".strip()
