"""单局对弈的控制器：落子、停一手、悔棋、认输、数子、胜负与棋谱记录。UI 无关。"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

from ..engine.ai import AI, RULE_CAPTURE, RULE_TERRITORY
from ..engine.stones import BLACK, KOMI, Move, Point, other
from .record import GameRecord

PHASE_PLAY = "play"
PHASE_SCORING = "scoring"   # 双方连续停一手后：标记死子、数子
PHASE_OVER = "over"


class GameController:
    def __init__(self, mode: str = "pve", rule: str = RULE_TERRITORY, size: int = 9,
                 capture_target: int = 5, black_name: str = "黑方", white_name: str = "白方",
                 difficulty: int = -1, setup: Optional[List[Tuple[str, int, int]]] = None):
        self.mode = mode
        self.rule = rule
        self.size = size
        self.capture_target = capture_target if rule == RULE_CAPTURE else 0
        self.record = GameRecord(mode=mode, rule=rule, size=size, komi=KOMI,
                                 capture_target=self.capture_target,
                                 black_name=black_name, white_name=white_name,
                                 difficulty=difficulty,
                                 setup=[list(s) for s in (setup or [])])
        self.board = self.record.build_start()
        self.history: List[tuple] = []                 # 每步之前的棋盘快照
        self.moves: List[Tuple[str, Move]] = []        # [(颜色, 着法)]
        self.captured_log: List[List[Point]] = []
        self.winner: Optional[str] = None              # 'b' / 'w' / 'draw'
        self.result_detail = ""
        self.phase = PHASE_PLAY
        self.dead: Set[Point] = set()

    # ---------- 状态 ----------
    @property
    def turn(self) -> str:
        return self.board.turn

    @property
    def last_move(self) -> Move:
        return self.moves[-1][1] if self.moves else None

    @property
    def last_color(self) -> Optional[str]:
        return self.moves[-1][0] if self.moves else None

    @property
    def over(self) -> bool:
        return self.phase == PHASE_OVER

    def is_legal(self, p: Point) -> bool:
        return self.phase == PHASE_PLAY and self.board.is_legal(p[0], p[1])

    # ---------- 落子 ----------
    def play(self, move: Move) -> List[Point]:
        """当前方落子（None = 停一手）。返回提掉的棋子。非法抛 IllegalMove。"""
        if self.phase != PHASE_PLAY:
            return []
        color = self.board.turn
        snap = self.board.snapshot()
        captured = self.board.play(move)
        self.history.append(snap)
        self.moves.append((color, move))
        self.captured_log.append(captured)
        self.record.add(color, move, len(captured))
        self._check_end(color)
        return captured

    def _check_end(self, color: str) -> None:
        b = self.board
        if self.rule == RULE_CAPTURE:
            if b.captures[color] >= self.capture_target:
                self._finish(color, f"先吃够 {self.capture_target} 子")
            elif b.passes >= 2:
                cb, cw = b.captures[BLACK], b.captures[other(BLACK)]
                if cb == cw:
                    self._finish("draw", "双方停一手，吃子数相同")
                else:
                    self._finish(BLACK if cb > cw else other(BLACK), "双方停一手，吃子更多")
        elif b.passes >= 2:
            self.phase = PHASE_SCORING
            self.dead = set()

    def resign(self, color: str) -> None:
        """color 方认输。"""
        if self.phase == PHASE_OVER:
            return
        self._finish(other(color), "中盘胜（对方认输）")

    def _finish(self, winner: str, detail: str) -> None:
        self.winner = winner
        self.result_detail = detail
        self.phase = PHASE_OVER
        self.record.result = winner
        self.record.result_detail = detail

    # ---------- 悔棋 ----------
    def undo_once(self) -> bool:
        if not self.history:
            return False
        self.board.restore(self.history.pop())
        self.moves.pop()
        self.captured_log.pop()
        self.record.pop()
        self.winner = None
        self.result_detail = ""
        self.record.result = None
        self.record.result_detail = ""
        self.phase = PHASE_PLAY
        self.dead = set()
        return True

    def undo_turn(self) -> bool:
        """人机模式下悔一整个回合（撤回电脑与自己的各一步）。"""
        undone = self.undo_once()
        if self.mode in ("pve", "puzzle"):
            undone = self.undo_once() or undone
        return undone

    # ---------- 数子 ----------
    def set_dead(self, dead: Set[Point]) -> None:
        self.dead = {p for p in dead if self.board.at(p) is not None}

    def toggle_dead(self, p: Point) -> bool:
        """点击一块棋：在“死子 / 活子”之间切换整块。"""
        if self.phase != PHASE_SCORING or self.board.at(p) is None:
            return False
        stones, _ = self.board.group(*p)
        if p in self.dead:
            self.dead -= stones
        else:
            self.dead |= stones
        return True

    def score_preview(self):
        """返回 (胜方, 胜几目, 黑子数, 白子数, 归属表)。"""
        black, white, owner = self.board.area_score(self.dead)
        diff = black - white - KOMI
        return (BLACK if diff > 0 else other(BLACK)), abs(diff), black, white, owner

    def confirm_score(self) -> None:
        if self.phase != PHASE_SCORING:
            return
        winner, margin, _b, _w, _o = self.score_preview()
        self._finish(winner, f"胜 {margin:g} 目")

    def resume_play(self) -> None:
        """数子阶段发现还有没下完的地方：回到对局，继续下。"""
        if self.phase != PHASE_SCORING:
            return
        self.phase = PHASE_PLAY
        self.dead = set()
        self.board.passes = 0

    # ---------- 提示 ----------
    def hint(self, color: Optional[str] = None) -> Move:
        if self.phase != PHASE_PLAY:
            return None
        color = color or self.board.turn
        helper = AI(difficulty=4, rule=self.rule, capture_target=self.capture_target)
        return helper.choose(self.board, color)
