"""内置电脑对手：规则启发 + 战术读子（不依赖外部引擎）。

- 吃子棋：电脑的主力，会提子、逃子、叫吃、征子，也会避免送吃。
- 正式对局：在没装 KataGo 时兜底使用，棋力入门水平。

难度主要由“是否读征子 / 是否看对方下一手”决定（低难度是“看不远”，而不是“乱下”）；
随机性只在几个分数接近的好点之间挑选，绝不会挑明显差的棋。
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from . import tactics
from .board import Board
from .stones import Move, Point, other

RULE_CAPTURE = "capture"      # 吃子棋
RULE_TERRITORY = "territory"  # 正式对局（数子）

# 难度：名称、是否读子、是否看对手应手、随机扰动（很小，只用来让下法不千篇一律）、
#       “次优”概率（只会在与最佳分差不超过 NEAR_BEST 的着法里换一手）
DIFFICULTIES = [
    ("入门", False, False, 2.0, 0.35),
    ("初级", True, False, 1.5, 0.25),
    ("中级", True, True, 1.0, 0.15),
    ("高级", True, True, 0.6, 0.05),
    ("大师", True, True, 0.3, 0.0),
]
NEAR_BEST = 6.0


def _influence(board: Board) -> Dict[Point, int]:
    """简单势力图：每个子向 3 格内辐射，正值偏黑、负值偏白。"""
    n = board.size
    inf: Dict[Point, int] = {}
    stones = [(r, c, board.grid[r][c]) for r in range(n) for c in range(n)
              if board.grid[r][c] is not None]
    for r in range(n):
        for c in range(n):
            if board.grid[r][c] is not None:
                continue
            v = 0
            for sr, sc, col in stones:
                d = abs(sr - r) + abs(sc - c)
                if d <= 3:
                    w = 4 - d
                    v += w if col == "b" else -w
            inf[(r, c)] = v
    return inf


class AI:
    def __init__(self, difficulty: int = 2, rule: str = RULE_TERRITORY,
                 capture_target: int = 5, rng: Optional[random.Random] = None):
        self.set_difficulty(difficulty)
        self.rule = rule
        self.capture_target = capture_target
        self.rng = rng or random.Random()

    def set_difficulty(self, level: int) -> None:
        level = max(0, min(level, len(DIFFICULTIES) - 1))
        self.level = level
        self.name, self.read, self.lookahead, self.noise, self.blunder = DIFFICULTIES[level]

    # ---------- 对外接口 ----------
    def choose(self, board: Board, color: str) -> Move:
        """为 color 方选一手棋；返回 None 表示停一手。"""
        b = board.clone()
        b.turn = color
        scored = self._score_all(b, color)
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][0]
        if self.rule == RULE_TERRITORY and self._should_pass(b, color, best):
            return None
        if self.blunder and self.rng.random() < self.blunder:
            near = [m for sc, m in scored[:4] if sc >= best - NEAR_BEST and sc > 0]
            if near:
                return self.rng.choice(near)
        return scored[0][1]

    # ---------- 打分 ----------
    def _score_all(self, b: Board, color: str) -> List[Tuple[float, Point]]:
        opp = other(color)
        n = b.size
        empty_board = b.is_empty_board()
        inf = _influence(b) if self.rule == RULE_TERRITORY else {}
        sign = 1 if color == "b" else -1
        urgent = self._urgent_moves(b, color) if self.read else {}
        my_stones = sum(1 for _ in b.stones_of(color))
        out: List[Tuple[float, Point]] = []
        for r in range(n):
            for c in range(n):
                if b.grid[r][c] is not None or not b.is_legal(r, c, color):
                    continue
                if b.is_eye(r, c, color):
                    continue            # 不填自己的眼
                s = self._score_move(b, color, opp, (r, c))
                if s is None:
                    continue
                s += urgent.get((r, c), 0.0)
                if self.rule == RULE_TERRITORY:
                    s += self._positional(b, (r, c), inf, sign, empty_board, my_stones)
                else:
                    s += self._capture_shape(b, (r, c), color)
                s += self.rng.gauss(0, self.noise)
                out.append((s, (r, c)))
        return out

    def _score_move(self, b: Board, color: str, opp: str, p: Point) -> Optional[float]:
        r, c = p
        # 落子前：相邻己方棋块是否在被叫吃
        saved_before = []
        atari_targets = []
        for nr, nc in b.neighbors(r, c):
            v = b.grid[nr][nc]
            if v == color:
                st, libs = b.group(nr, nc)
                if len(libs) == 1:
                    saved_before.append(len(st))
        snap = b.snapshot()
        captured = b.play(p)
        s = 0.0
        ncap = len(captured)
        win_cap = (self.rule == RULE_CAPTURE and
                   b.captures[color] >= self.capture_target)
        if win_cap:
            b.restore(snap)
            return 100000.0
        s += ncap * (60 if self.rule == RULE_CAPTURE else 30)
        st, libs = b.group(r, c)
        nlibs = len(libs)
        # 送吃：自己只剩一气（除非刚提了子形成打劫）
        if nlibs == 1 and ncap == 0:
            s -= 50 * len(st) + (80 if self.rule == RULE_CAPTURE else 10)
        elif nlibs == 2 and self.rule == RULE_CAPTURE:
            s -= 6 * len(st)
        # 救子：原先被叫吃的己方棋块现在 ≥2 气
        if saved_before and nlibs >= 2:
            s += sum(saved_before) * (45 if self.rule == RULE_CAPTURE else 25)
        # 叫吃对方
        seen = set()
        for nr, nc in b.neighbors(r, c):
            if b.grid[nr][nc] == opp and (nr, nc) not in seen:
                ost, olibs = b.group(nr, nc)
                seen |= ost
                if len(olibs) == 1:
                    atari_targets.append(len(ost))
                elif len(olibs) == 2 and self.rule == RULE_CAPTURE:
                    s += 3 * len(ost)
        if atari_targets and nlibs >= 2:
            s += sum(atari_targets) * (18 if self.rule == RULE_CAPTURE else 8)
        s += min(nlibs, 4) * (3 if self.rule == RULE_CAPTURE else 1.5)
        # 看对方下一手：对方能否立刻吃掉我的子
        if self.lookahead:
            s -= self._opp_threat(b, color) * (0.9 if self.rule == RULE_CAPTURE else 0.5)
        b.restore(snap)
        return s

    def _opp_threat(self, b: Board, color: str) -> float:
        """对方下一手最多能吃掉我多少子（已被叫吃的棋块）。"""
        worst = 0
        for st, libs in b.groups_of(color):
            if len(libs) == 1:
                p = next(iter(libs))
                if b.is_legal(p[0], p[1], other(color)):
                    worst = max(worst, len(st))
        if self.rule == RULE_CAPTURE and worst and \
                b.captures[other(color)] + worst >= self.capture_target:
            return 5000
        return worst * 55

    def _urgent_moves(self, b: Board, color: str) -> Dict[Point, float]:
        """战术要点：能征吃/枪吃对方的着点、把己方危棋救出来的着点。"""
        opp = other(color)
        bonus: Dict[Point, float] = {}
        k = 60 if self.rule == RULE_CAPTURE else 25
        for st, libs in b.groups_of(opp):
            if len(libs) == 2:
                t = next(iter(st))
                m = tactics.capture_move(b, t, budget=800)
                if m is not None:
                    bonus[m] = bonus.get(m, 0) + k * len(st) + 20
        for st, libs in b.groups_of(color):
            if len(libs) <= 2:
                t = next(iter(st))
                bb = b.clone()
                bb.turn = opp
                if tactics.capture_move(bb, t, budget=800) is not None:
                    m = tactics.escape_move(b, t, budget=800)
                    if m is not None:
                        bonus[m] = bonus.get(m, 0) + k * len(st) + 20
        return bonus

    def _capture_shape(self, b: Board, p: Point, color: str) -> float:
        """吃子棋的形状分：贴近对方、不贴边。"""
        r, c = p
        n = b.size
        edge = min(r, c, n - 1 - r, n - 1 - c)
        s = -6 if edge == 0 else 0
        opp = other(color)
        near = 0
        for nr, nc in b.neighbors(r, c):
            if b.grid[nr][nc] == opp:
                near += 1
        s += near * 2
        if b.is_empty_board():
            mid = n // 2
            s -= (abs(r - mid) + abs(c - mid)) * 2
        return s

    def _positional(self, b: Board, p: Point, inf: Dict[Point, int], sign: int,
                    empty_board: bool, my_stones: int) -> float:
        """正式对局的大局观（很朴素）：开局占角边、中盘扩张/压缩势力、不进对方铁空。"""
        r, c = p
        n = b.size
        line = min(r, c, n - 1 - r, n - 1 - c)   # 0 = 一线
        opening = my_stones < (4 if n == 9 else 8 if n == 13 else 12)
        s = 0.0
        if line == 0:
            s -= 12
        elif line == 1:
            s -= 4 if not opening else 8
        if opening:
            good = (2, 3) if n >= 13 else (2,)
            if line in good:
                s += 10
            if n == 9 and line == 4:
                s += 6     # 九路天元也不错
        v = inf.get(p, 0) * sign
        # 自己势力很强的地方是“自己的空”，不要填；对方的铁空也别进
        if v >= 8:
            s -= 25
        elif v <= -9:
            s -= 18
        else:
            # 势力交界处最有价值
            s += 8 - abs(v)
        return s

    def _should_pass(self, b: Board, color: str, best: float) -> bool:
        if b.passes > 0:
            # 对方已停一手：自己领先或已无好棋就停
            winner, _, _, _ = b.score_result()
            if winner == color or best < 4:
                return True
        return best < -2
