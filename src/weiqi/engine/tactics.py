"""战术读子：判断一块棋能否被吃掉（叫吃、征子、枪吃等），以及如何逃跑。

只读“气数不多（≤2 气）”的局部战斗，用节点预算限制搜索量，读不清的一律视为“吃不掉”。
供内置 AI、吃子棋、教学练习题使用。
"""
from __future__ import annotations

from typing import List, Optional

from .board import Board
from .stones import Point, other

DEFAULT_DEPTH = 40      # 征子在 19 路上可能很长
DEFAULT_BUDGET = 2500   # 每次读子最多搜索的节点数


class _Budget:
    __slots__ = ("left",)

    def __init__(self, n: int):
        self.left = n


def _play_as(b: Board, p: Point, color: str) -> bool:
    """以 color 方在 p 落子（无视轮次）；不合法返回 False。"""
    b.turn = color
    if not b.is_legal(p[0], p[1], color):
        return False
    b.play(p)
    return True


def _adjacent_in_atari(b: Board, stones, color: str) -> List[Point]:
    """与这块棋相邻、只剩一气的 color 方棋块的那口气（吃掉它可以解围）。"""
    out = []
    seen = set()
    for (r, c) in stones:
        for nr, nc in b.neighbors(r, c):
            if b.grid[nr][nc] == color and (nr, nc) not in seen:
                st, libs = b.group(nr, nc)
                seen |= st
                if len(libs) == 1:
                    out.extend(libs)
    return out


def _attack(b: Board, target: Point, depth: int, budget: _Budget) -> Optional[Point]:
    """进攻方先走：返回能吃掉 target 所在棋块的着点，否则 None。"""
    budget.left -= 1
    color = b.at(target)
    if color is None:
        return None
    attacker = other(color)
    stones, libs = b.group(*target)
    if len(libs) == 1:
        p = next(iter(libs))
        return p if b.is_legal(p[0], p[1], attacker) else None
    if len(libs) > 2 or depth <= 0 or budget.left <= 0:
        return None
    # 两气：依次试紧每一口气（先试紧完后对方气更少的那口）
    for p in sorted(libs):
        snap = b.snapshot()
        if _play_as(b, p, attacker):
            # 自己刚下的子若被反提（只剩 1 气且对方能吃），交给防守方处理
            if _defend(b, target, depth - 1, budget) is None:
                b.restore(snap)
                return p
        b.restore(snap)
        if budget.left <= 0:
            break
    return None


def _defend(b: Board, target: Point, depth: int, budget: _Budget) -> Optional[Point]:
    """防守方先走：返回能救活 target 棋块的着点；救不了返回 None。

    若该块棋本来就不危险（≥3 气）返回 target 自身作为“安全”标记。
    """
    budget.left -= 1
    color = b.at(target)
    if color is None:
        return None
    stones, libs = b.group(*target)
    if len(libs) >= 3:
        return target
    if depth <= 0 or budget.left <= 0:
        return target          # 读不清，视为能活
    attacker = other(color)
    candidates = _adjacent_in_atari(b, stones, attacker) + sorted(libs)
    tried = set()
    for p in candidates:
        if p in tried:
            continue
        tried.add(p)
        snap = b.snapshot()
        if _play_as(b, p, color):
            if b.at(target) is not None and _attack(b, target, depth - 1, budget) is None:
                b.restore(snap)
                return p
        b.restore(snap)
        if budget.left <= 0:
            return target
    return None


def capture_move(board: Board, target: Point, depth: int = DEFAULT_DEPTH,
                 budget: int = DEFAULT_BUDGET) -> Optional[Point]:
    """进攻方先走时吃掉 target 棋块的着点（含征子、枪吃），没有返回 None。"""
    b = board.clone()
    b.ko = None if board.at(target) == board.turn else board.ko
    return _attack(b, target, depth, _Budget(budget))


def can_capture(board: Board, target: Point, **kw) -> bool:
    return capture_move(board, target, **kw) is not None


def escape_move(board: Board, target: Point, depth: int = DEFAULT_DEPTH,
                budget: int = DEFAULT_BUDGET) -> Optional[Point]:
    """防守方先走时救出 target 棋块的着点。

    返回 None 表示已经救不了；本来就安全时也返回 None（不需要专门逃）。
    """
    b = board.clone()
    res = _defend(b, target, depth, _Budget(budget))
    if res is None or res == target:
        return None
    return res


def is_dead_lost(board: Board, target: Point, **kw) -> bool:
    """防守方先走也救不出来（例如已被征死）。"""
    b = board.clone()
    return _defend(b, target, kw.get("depth", DEFAULT_DEPTH),
                   _Budget(kw.get("budget", DEFAULT_BUDGET))) is None
