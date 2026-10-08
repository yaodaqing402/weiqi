"""围棋基础常量：颜色、棋盘尺寸、坐标工具。

棋盘坐标：(row, col)，row 0 在最上方，col 0 在最左侧。
“停一手”（虚着）用 None 表示。
"""
from __future__ import annotations

from typing import Optional, Tuple

# 阵营
BLACK = "b"
WHITE = "w"

# 支持的棋盘尺寸
SIZES = (9, 13, 19)

# 中国规则贴目（黑贴 3¾ 子 = 7.5 目）
KOMI = 7.5

# 落点；None 表示停一手
Point = Tuple[int, int]
Move = Optional[Point]

# GTP / 记谱用列字母（跳过 I）
COL_LETTERS = "ABCDEFGHJKLMNOPQRST"


def other(color: str) -> str:
    return WHITE if color == BLACK else BLACK


def color_name(color: str) -> str:
    return "黑方" if color == BLACK else "白方"


def star_points(size: int):
    """星位（含天元）。"""
    if size == 19:
        idx = (3, 9, 15)
    elif size == 13:
        idx = (3, 6, 9)
    elif size == 9:
        return [(2, 2), (2, 6), (6, 2), (6, 6), (4, 4)]
    else:
        return []
    return [(r, c) for r in idx for c in idx]
