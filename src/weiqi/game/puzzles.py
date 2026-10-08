"""教学练习题：吃子基本功闯关（叫吃、双叫吃、征子、枪吃、倒扑）。

玩家执黑先行，目标是吃掉标记的白子（▲）。白棋由电脑拼命逃跑。
每道题的棋形都用读子器验证过“有解且解法唯一/明确”（见 tests/test_engine.py）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..engine import tactics
from ..engine.ai import AI, RULE_CAPTURE
from ..engine.board import Board
from ..engine.stones import BLACK, WHITE, Move, Point


@dataclass
class Puzzle:
    name: str
    tip: str
    rows: List[str]                  # 'X' 黑子、'O' 白子、'@' 目标白子、'.' 空
    max_moves: int                   # 黑棋最多下几手
    need: int = 1                    # 没有目标子时：吃够几子过关

    @property
    def size(self) -> int:
        return len(self.rows)

    @property
    def target(self) -> Optional[Point]:
        for r, row in enumerate(self.rows):
            c = row.find("@")
            if c >= 0:
                return (r, c)
        return None

    def setup(self) -> List[Tuple[str, int, int]]:
        out = []
        for r, row in enumerate(self.rows):
            for c, ch in enumerate(row):
                if ch == "X":
                    out.append((BLACK, r, c))
                elif ch in "O@":
                    out.append((WHITE, r, c))
        return out

    def build_board(self) -> Board:
        b = Board(self.size)
        for color, r, c in self.setup():
            b.grid[r][c] = color
        b.turn = BLACK
        return b

    # ---------- 判定 ----------
    def solved(self, board: Board) -> bool:
        t = self.target
        if t is not None:
            return board.at(t) != WHITE
        return board.captures[BLACK] >= self.need

    def escaped(self, board: Board, black_moves: int) -> bool:
        """白棋逃掉（气长到 4 口以上）或黑棋步数用完。"""
        if black_moves >= self.max_moves and not self.solved(board):
            return True
        t = self.target
        if t is not None and board.at(t) == WHITE:
            return board.liberty_count(*t) >= 4
        return False


def defender_move(puzzle: Puzzle, board: Board) -> Move:
    """白棋应手：目标子危险时拼命长气 / 提子解围，否则交给吃子棋 AI。"""
    t = puzzle.target
    if t is not None and board.at(t) == WHITE:
        m = tactics.escape_move(board, t)
        if m is not None:
            return m
        stones, libs = board.group(*t)
        if len(libs) <= 2:
            # 救不了也要挣扎：选长出后气最多的点（或提掉叫吃自己的黑子）
            best, best_libs = None, -1
            cands = set(libs)
            for (r, c) in stones:
                for nr, nc in board.neighbors(r, c):
                    if board.grid[nr][nc] == BLACK:
                        st, bl = board.group(nr, nc)
                        if len(bl) == 1:
                            cands |= bl
            for p in sorted(cands):
                if not board.is_legal(p[0], p[1], WHITE):
                    continue
                bb = board.clone()
                bb.play(p)
                n = bb.liberty_count(*t) if bb.at(t) == WHITE else -1
                if n > best_libs:
                    best, best_libs = p, n
            if best is not None:
                return best
    return AI(4, rule=RULE_CAPTURE, capture_target=99).choose(board, WHITE)


def solution_move(puzzle: Puzzle, board: Board) -> Move:
    """黑棋的正解着点（供“提示”与测试）：直接吃 / 征子 / 枪吃 / 双叫吃。"""
    t = puzzle.target
    targets = [t] if t is not None and board.at(t) == WHITE else \
        [next(iter(st)) for st, _l in board.groups_of(WHITE)]
    for tp in targets:
        m = tactics.capture_move(board, tp)
        if m is not None:
            return m
    # 枪吃：不贴着叫吃，但下完后白棋怎么逃都逃不掉
    for tp in targets:
        tr, tc = tp
        for p in board.legal_moves(BLACK):
            if abs(p[0] - tr) + abs(p[1] - tc) > 3:
                continue
            bb = board.clone()
            bb.play(p)
            if bb.at(tp) != WHITE or tactics.is_dead_lost(bb, tp):
                return p
    # 双叫吃：一手同时叫吃两块
    for p in board.legal_moves(BLACK):
        bb = board.clone()
        bb.play(p)
        if sum(1 for _s, l in bb.groups_of(WHITE) if len(l) == 1) >= 2:
            return p
    return None


PUZZLES: List[Puzzle] = [
    Puzzle(
        name="第1关 · 叫吃提子",
        tip="白子只剩最后一口气了！找到那口气，下在那里就能把它提掉。",
        rows=[
            ".........",
            ".........",
            ".........",
            "....X....",
            "...X@X...",
            ".........",
            ".........",
            ".........",
            ".........",
        ],
        max_moves=1,
    ),
    Puzzle(
        name="第2关 · 双叫吃",
        tip="一步棋同时叫吃两块白棋，白棋只能救一边，另一边就归你啦。",
        rows=[
            ".........",
            ".........",
            "...X.X...",
            "...O.O...",
            "...X.X...",
            ".........",
            ".........",
            ".........",
            ".........",
        ],
        max_moves=2,
    ),
    Puzzle(
        name="第3关 · 征子",
        tip="从正确的方向叫吃，白棋越逃气越少，一路追到边上就吃掉啦。方向错了白棋就跑了哦！",
        rows=[
            ".........",
            ".........",
            "...XX....",
            "...@.....",
            "...X.....",
            ".........",
            ".........",
            ".........",
            ".........",
        ],
        max_moves=12,
    ),
    Puzzle(
        name="第4关 · 枪吃（门吃）",
        tip="四个角的白子会接应，直接追着叫吃会被白棋逃掉。试试不贴着白子，从远一点的地方把它“关在门里”。",
        rows=[
            ".........",
            ".O.....O.",
            ".........",
            "...X.....",
            "...X@.X..",
            "....X....",
            ".........",
            ".O.....O.",
            ".........",
        ],
        max_moves=4,
    ),
    Puzzle(
        name="第5关 · 倒扑",
        tip="先往白棋的虎口里送一颗子让它吃，吃完白棋反而只剩一口气，你再提回来就吃掉一大块！",
        rows=[
            ".........",
            ".........",
            ".........",
            ".........",
            ".........",
            ".........",
            "..OOX....",
            "XOO.@X...",
            "XXX.OX...",
        ],
        max_moves=2,
    ),
]


def clean_puzzles() -> List[Puzzle]:
    """去掉摆子非法（有棋块没气）的关卡（构造期自检兜底）。"""
    valid = []
    for p in PUZZLES:
        b = p.build_board()
        ok = all(libs for color in (BLACK, WHITE) for _st, libs in b.groups_of(color))
        if ok:
            valid.append(p)
    return valid
