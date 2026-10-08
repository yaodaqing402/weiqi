"""围棋棋盘：落子、提子、禁着点（自杀 / 打劫）、停一手、数子。

规则采用中国规则：禁止自杀，简单劫（不能立即回提），数子法计算胜负。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from .stones import BLACK, WHITE, KOMI, Move, Point, other

_NEIGHBOR_CACHE: Dict[int, List[List[List[Point]]]] = {}


def _neighbor_table(size: int) -> List[List[List[Point]]]:
    if size not in _NEIGHBOR_CACHE:
        table = []
        for r in range(size):
            row = []
            for c in range(size):
                ns = []
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < size and 0 <= nc < size:
                        ns.append((nr, nc))
                row.append(ns)
            table.append(row)
        _NEIGHBOR_CACHE[size] = table
    return _NEIGHBOR_CACHE[size]


class IllegalMove(ValueError):
    pass


class Board:
    def __init__(self, size: int = 9):
        self.size = size
        self.grid: List[List[Optional[str]]] = [[None] * size for _ in range(size)]
        self.turn = BLACK
        self.ko: Optional[Point] = None          # 当前走子方不能落的劫点
        self.captures = {BLACK: 0, WHITE: 0}     # 各方累计提子数
        self.passes = 0                          # 连续停一手次数
        self._nb = _neighbor_table(size)

    # ---------- 复制 / 快照 ----------
    def clone(self) -> "Board":
        b = Board.__new__(Board)
        b.size = self.size
        b.grid = [row[:] for row in self.grid]
        b.turn = self.turn
        b.ko = self.ko
        b.captures = dict(self.captures)
        b.passes = self.passes
        b._nb = self._nb
        return b

    def snapshot(self) -> tuple:
        return ([row[:] for row in self.grid], self.turn, self.ko,
                dict(self.captures), self.passes)

    def restore(self, snap: tuple) -> None:
        grid, self.turn, self.ko, caps, self.passes = snap
        self.grid = [row[:] for row in grid]
        self.captures = dict(caps)

    # ---------- 基础查询 ----------
    def neighbors(self, r: int, c: int) -> List[Point]:
        return self._nb[r][c]

    def at(self, p: Point) -> Optional[str]:
        return self.grid[p[0]][p[1]]

    def group(self, r: int, c: int) -> Tuple[Set[Point], Set[Point]]:
        """返回 (r,c) 所在棋块的 (棋子集合, 气集合)。"""
        color = self.grid[r][c]
        if color is None:
            return set(), set()
        stones = {(r, c)}
        libs: Set[Point] = set()
        stack = [(r, c)]
        grid = self.grid
        nb = self._nb
        while stack:
            cr, cc = stack.pop()
            for nr, nc in nb[cr][cc]:
                v = grid[nr][nc]
                if v is None:
                    libs.add((nr, nc))
                elif v == color and (nr, nc) not in stones:
                    stones.add((nr, nc))
                    stack.append((nr, nc))
        return stones, libs

    def liberty_count(self, r: int, c: int) -> int:
        return len(self.group(r, c)[1])

    def stones_of(self, color: str) -> Iterable[Point]:
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == color:
                    yield (r, c)

    def groups_of(self, color: str) -> List[Tuple[Set[Point], Set[Point]]]:
        seen: Set[Point] = set()
        out = []
        for p in self.stones_of(color):
            if p in seen:
                continue
            st, libs = self.group(*p)
            seen |= st
            out.append((st, libs))
        return out

    def is_empty_board(self) -> bool:
        return all(v is None for row in self.grid for v in row)

    # ---------- 合法性 ----------
    def is_legal(self, r: int, c: int, color: Optional[str] = None) -> bool:
        color = color or self.turn
        if not (0 <= r < self.size and 0 <= c < self.size):
            return False
        if self.grid[r][c] is not None:
            return False
        if color == self.turn and self.ko == (r, c):
            return False
        grid = self.grid
        opp = other(color)
        # 有空邻点必然有气，合法
        for nr, nc in self._nb[r][c]:
            if grid[nr][nc] is None:
                return True
        # 试落：能提子或连到有其它气的己方棋块即合法
        grid[r][c] = color
        try:
            for nr, nc in self._nb[r][c]:
                v = grid[nr][nc]
                if v == opp and len(self.group(nr, nc)[1]) == 0:
                    return True
            return len(self.group(r, c)[1]) > 0
        finally:
            grid[r][c] = None

    def legal_moves(self, color: Optional[str] = None) -> List[Point]:
        color = color or self.turn
        return [(r, c) for r in range(self.size) for c in range(self.size)
                if self.grid[r][c] is None and self.is_legal(r, c, color)]

    # ---------- 落子 ----------
    def play(self, move: Move) -> List[Point]:
        """当前走子方落子（None 表示停一手），返回被提掉的棋子列表。非法则抛 IllegalMove。"""
        if move is None:
            self.passes += 1
            self.ko = None
            self.turn = other(self.turn)
            return []
        r, c = move
        color = self.turn
        if not self.is_legal(r, c, color):
            raise IllegalMove(f"illegal move {move} for {color}")
        opp = other(color)
        grid = self.grid
        grid[r][c] = color
        captured: List[Point] = []
        for nr, nc in self._nb[r][c]:
            if grid[nr][nc] == opp:
                st, libs = self.group(nr, nc)
                if not libs:
                    for (sr, sc) in st:
                        grid[sr][sc] = None
                    captured.extend(st)
        self.captures[color] += len(captured)
        # 简单劫：只提一子、且落下的子单独成块只剩一气（即该被提点）
        self.ko = None
        if len(captured) == 1:
            st, libs = self.group(r, c)
            if len(st) == 1 and len(libs) == 1:
                self.ko = captured[0]
        self.passes = 0
        self.turn = opp
        return captured

    # ---------- 眼位 ----------
    def is_eye(self, r: int, c: int, color: str) -> bool:
        """粗略判断空点 (r,c) 是否为 color 方的真眼（避免电脑自填眼）。"""
        if self.grid[r][c] is not None:
            return False
        for nr, nc in self._nb[r][c]:
            if self.grid[nr][nc] != color:
                return False
        opp = other(color)
        bad = 0
        diag = 0
        for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                diag += 1
                if self.grid[nr][nc] == opp:
                    bad += 1
        # 边角上斜对角只要有一个敌子就是假眼；中腹允许一个
        return bad == 0 if diag < 4 else bad <= 1

    # ---------- 数子（中国规则）----------
    def area_score(self, dead: Optional[Set[Point]] = None
                   ) -> Tuple[int, int, Dict[Point, Optional[str]]]:
        """数子：返回 (黑方子数, 白方子数, 每个空点/死子点的归属)。

        dead 中的棋子视为死子，先从棋盘上拿掉再数。归属为 None 表示单官（双方都不占）。
        """
        dead = dead or set()
        grid = [row[:] for row in self.grid]
        for (r, c) in dead:
            grid[r][c] = None
        owner: Dict[Point, Optional[str]] = {}
        black = white = 0
        seen: Set[Point] = set()
        for r in range(self.size):
            for c in range(self.size):
                v = grid[r][c]
                if v == BLACK:
                    black += 1
                elif v == WHITE:
                    white += 1
                elif (r, c) not in seen:
                    region = {(r, c)}
                    stack = [(r, c)]
                    borders = set()
                    while stack:
                        cr, cc = stack.pop()
                        for nr, nc in self._nb[cr][cc]:
                            w = grid[nr][nc]
                            if w is None:
                                if (nr, nc) not in region:
                                    region.add((nr, nc))
                                    stack.append((nr, nc))
                            else:
                                borders.add(w)
                    seen |= region
                    who = borders.pop() if len(borders) == 1 else None
                    for p in region:
                        owner[p] = who
                    if who == BLACK:
                        black += len(region)
                    elif who == WHITE:
                        white += len(region)
        return black, white, owner

    def score_result(self, dead: Optional[Set[Point]] = None, komi: float = KOMI
                     ) -> Tuple[str, float, int, int]:
        """返回 (胜方, 胜多少目, 黑子数, 白子数)。贴目为小数，不会和棋。"""
        black, white, _ = self.area_score(dead)
        diff = black - white - komi
        return (BLACK if diff > 0 else WHITE), abs(diff), black, white
