"""对局场景：支持人机、双人、局域网联机、吃子练习四种模式；吃子棋 / 正式对局两种玩法。"""
from __future__ import annotations

import queue
import threading
from typing import Callable, Dict, List, Optional

import pygame

from .. import theme
from ..app import Scene
from ..board_view import BoardView
from ..widgets import Button
from ...engine import katago
from ...engine.ai import AI, DIFFICULTIES, RULE_CAPTURE, RULE_TERRITORY
from ...engine.board import IllegalMove
from ...engine.stones import BLACK, KOMI, WHITE, Move, Point, color_name, other
from ...game import rank
from ...game.controller import GameController, PHASE_PLAY, PHASE_SCORING
from ...game.record import save_record

FRESH_DUR = 0.15      # 落子“啪”一下的动画时长
AI_MIN_DELAY = 0.35   # 电脑至少“想”这么久，免得落子太突然
GREY = (150, 120, 90)


class GameScene(Scene):
    def __init__(self, app, mode: str = "pvp", rule: str = RULE_CAPTURE, size: int = 9,
                 capture_target: int = 3, difficulty: int = -1, human_color: str = BLACK,
                 puzzle_index: Optional[int] = None, net=None, use_engine: bool = True):
        super().__init__(app)
        self.mode = mode
        self.rule = rule
        self.size = size
        self.capture_target = capture_target
        self.difficulty = difficulty
        self.human_color = human_color
        self.puzzle_index = puzzle_index
        self.net = net
        self.use_engine = use_engine
        self.engine: Optional[katago.KataGo] = None      # 人机正式对局的对手引擎
        self.helper: Optional[katago.KataGo] = None      # 双人/联机时用于提示、数子的引擎

    # ---------- 初始化 ----------
    def on_enter(self) -> None:
        self._close_engines()
        self._setup_controller()
        self.view = BoardView(self.size)
        self.hover: Optional[Point] = None
        self.fresh: Optional[list] = None
        self._pending_check = False
        self.busy: Dict[str, bool] = {}
        self._results: "queue.Queue[tuple]" = queue.Queue()
        self._ai_wait = 0.0
        self.hint_point: Optional[Point] = None
        self.hint_timer = 0.0
        self.message = ""
        self.message_timer = 0.0
        self.end_dialog = None
        self._awarded = False
        self._saved = False
        self._dead_estimated = False
        self.engine_state = "none"          # none / starting / ready / failed
        self.engine_note = ""
        self._buttons_phase = None
        self._build_buttons()
        if self._wants_engine():
            self._start_engine()

    def on_exit(self) -> None:
        if self.mode == "lan" and self.net:
            self.net.close()
        self._close_engines()

    def _close_engines(self) -> None:
        for e in (self.engine, self.helper):
            if e is not None:
                threading.Thread(target=e.close, daemon=True).start()
        self.engine = None
        self.helper = None

    def _setup_controller(self) -> None:
        pn = self.app.settings.get("player_name", "小棋手")
        setup = None
        if self.mode == "puzzle":
            from ...game.puzzles import clean_puzzles
            self.puzzle = clean_puzzles()[self.puzzle_index or 0]
            self.rule, self.size = RULE_CAPTURE, self.puzzle.size
            self.capture_target = 999
            self.human_color, self.ai_color = BLACK, WHITE
            setup = self.puzzle.setup()
            black, white = pn, "电脑"
        elif self.mode == "pve":
            ai_name = DIFFICULTIES[max(0, self.difficulty)][0]
            black = pn if self.human_color == BLACK else f"电脑·{ai_name}"
            white = pn if self.human_color == WHITE else f"电脑·{ai_name}"
            self.ai_color = other(self.human_color)
            self.ai = AI(self.difficulty, rule=self.rule, capture_target=self.capture_target)
        elif self.mode == "lan":
            self.human_color = self.net.color
            black = pn if self.human_color == BLACK else "对手"
            white = pn if self.human_color == WHITE else "对手"
            self.ai_color = None
        else:
            black, white = pn, "挑战者"
            self.ai_color = None
        self.ctrl = GameController(self.mode, rule=self.rule, size=self.size,
                                   capture_target=self.capture_target,
                                   black_name=black, white_name=white,
                                   difficulty=self.difficulty, setup=setup)

    # ---------- KataGo ----------
    def _wants_engine(self) -> bool:
        return (self.use_engine and self.mode == "pve" and self.rule == RULE_TERRITORY
                and katago.is_available(self.app.settings))

    def _start_engine(self) -> None:
        self.engine_state = "starting"
        eng = katago.KataGo(level=max(0, self.difficulty), settings=self.app.settings)
        self.engine = eng

        def work():
            eng.start()
            return eng
        self._spawn("engine", work)

    def _helper_engine(self) -> Optional[katago.KataGo]:
        """提示 / 数子用的引擎：人机时复用对手引擎，否则按需启动一个较强的。"""
        if self.engine is not None and self.engine_state == "ready":
            return self.engine
        if self.mode == "pve" or not self.use_engine or self.rule != RULE_TERRITORY:
            return None
        if self.helper is None:
            if not katago.is_available(self.app.settings):
                return None
            self.helper = katago.KataGo(level=4, settings=self.app.settings, prefer_human=False)
        if not self.helper.alive:
            self.helper.start()
        return self.helper

    # ---------- 后台任务 ----------
    def _spawn(self, kind: str, fn: Callable) -> None:
        self.busy[kind] = True

        def run():
            try:
                self._results.put((kind, fn(), None))
            except Exception as e:  # 引擎/读子出错都在主线程里兜底
                self._results.put((kind, None, e))
        threading.Thread(target=run, daemon=True).start()

    def _drain_results(self) -> None:
        while True:
            try:
                kind, value, err = self._results.get_nowait()
            except queue.Empty:
                return
            self.busy[kind] = False
            getattr(self, f"_on_{kind}")(value, err)

    def _on_engine(self, eng, err) -> None:
        if eng is not self.engine:
            return          # 已经重新开局，旧引擎的结果作废
        if err is None:
            self.engine_state = "ready"
            human = "人类风格" if eng.uses_human else "搜索量分档"
            self.engine_note = f"KataGo · {human}"
        else:
            self.engine_state = "failed"
            self.engine_note = "KataGo 启动失败，改用内置 AI"
            self._flash(str(err)[:40])
            self.engine = None

    # ---------- 按钮 ----------
    def _build_buttons(self) -> None:
        phase = self.ctrl.phase
        self._buttons_phase = phase
        x = theme.PANEL_X + 24
        w = theme.WIDTH - theme.PANEL_X - 48
        half = (w - 16) // 2
        y0 = theme.HEIGHT - 186
        rows: List[List[tuple]]
        if phase == PHASE_SCORING:
            rows = [[("确认结果", self._confirm_score, theme.BTN),
                     ("继续下棋", self._resume_play, GREY)],
                    [("返回菜单", self._to_menu, GREY)]]
        elif self.mode == "puzzle":
            rows = [[("悔棋", self._undo, theme.BTN), ("提示", self._hint, theme.BTN)],
                    [("重新开始", self._restart, GREY), ("返回菜单", self._to_menu, GREY)]]
        elif self.mode == "lan":
            rows = [[("停一手", self._pass, theme.BTN), ("提示", self._hint, theme.BTN)],
                    [("认输", self._resign, (170, 80, 70)), ("返回菜单", self._to_menu, GREY)]]
        else:
            rows = [[("停一手", self._pass, theme.BTN), ("悔棋", self._undo, theme.BTN)],
                    [("提示", self._hint, theme.BTN), ("认输", self._resign, (170, 80, 70))],
                    [("重新开始", self._restart, GREY), ("返回菜单", self._to_menu, GREY)]]
        y0 = theme.HEIGHT - 24 - len(rows) * 58 + 12
        self.buttons = []
        for i, row in enumerate(rows):
            y = y0 + i * 58
            for j, (label, cb, col) in enumerate(row):
                bw = w if len(row) == 1 else half
                self.buttons.append(Button((x + j * (half + 16), y, bw, 46), label, cb,
                                           font_size=20, color=col))
        self._list_bottom = y0 - 40

    # ---------- 按钮动作 ----------
    def _idle(self) -> bool:
        return not self.fresh and not self.busy.get("ai") and not self.end_dialog

    def _my_turn(self) -> bool:
        if self.mode == "pvp":
            return True
        return self.ctrl.turn == self.human_color

    def _pass(self) -> None:
        if not self._idle() or self.ctrl.phase != PHASE_PLAY or not self._my_turn():
            return
        self.app.sound.play("button")
        self._apply_move(None, local=True)

    def _undo(self) -> None:
        if not self._idle() or self.mode == "lan":
            return
        ok = self.ctrl.undo_turn() if self.mode in ("pve", "puzzle") else self.ctrl.undo_once()
        if self.mode == "pve" and ok and self.ctrl.turn != self.human_color:
            self.ctrl.undo_once()       # 电脑刚停一手等情况：退回到自己走
        if ok:
            self.app.sound.play("button")
            self.hint_point = None
            self._dead_estimated = False
            self.message = ""

    def _hint(self) -> None:
        if not self._idle() or self.busy.get("hint") or self.ctrl.phase != PHASE_PLAY:
            return
        if not self._my_turn():
            return
        self.app.sound.play("button")
        color = self.ctrl.turn
        board = self.ctrl.board.clone()
        moves = list(self.ctrl.moves)
        if self.mode == "puzzle":
            from ...game.puzzles import solution_move
            self._spawn("hint", lambda: solution_move(self.puzzle, board))
            return
        if self.rule == RULE_TERRITORY and self.use_engine:
            def work():
                try:
                    eng = self._helper_engine()
                    if eng is not None:
                        mv = eng.genmove(self.size, moves, color)
                        return None if mv == "resign" else mv
                except katago.EngineError:
                    pass
                return AI(4, rule=self.rule).choose(board, color)
            self._flash("提示计算中…", 10)
            self._spawn("hint", work)
            return
        cap = self.capture_target
        self._spawn("hint", lambda: AI(4, rule=self.rule, capture_target=cap).choose(board, color))

    def _on_hint(self, mv, err) -> None:
        if self.message == "提示计算中…":
            self.message = ""
        if err is not None or self.ctrl.phase != PHASE_PLAY:
            return
        if mv is None:
            self._flash("建议：停一手")
        else:
            self.hint_point = mv
            self.hint_timer = 3.0

    def _resign(self) -> None:
        if self.ctrl.over or self.mode == "puzzle":
            return
        if self.mode == "lan" and self.net:
            self.net.send_resign()
        loser = self.ctrl.turn if self.mode == "pvp" else self.human_color
        self.ctrl.resign(loser)
        self._open_end_dialog()

    def _restart(self) -> None:
        self.app.sound.play("button")
        if self.mode == "lan":
            self._to_menu()
            return
        self.on_enter()

    def _to_menu(self) -> None:
        self.app.sound.play("button")
        from .menu import MenuScene
        self.app.go(MenuScene(self.app))

    # ---------- 数子阶段 ----------
    def _confirm_score(self, from_net: bool = False) -> None:
        if self.ctrl.phase != PHASE_SCORING or self.busy.get("dead"):
            return
        if self.mode == "lan" and self.net and not from_net:
            self.net.send({"type": "score_confirm"})
        self.ctrl.confirm_score()
        self._on_game_over()

    def _resume_play(self, from_net: bool = False) -> None:
        if self.ctrl.phase != PHASE_SCORING:
            return
        if self.mode == "lan" and self.net and not from_net:
            self.net.send({"type": "score_resume"})
        self.app.sound.play("button")
        self.ctrl.resume_play()
        self._dead_estimated = False
        self._flash("继续下棋：把没下完的地方下完吧")

    def _estimate_dead(self) -> None:
        self._dead_estimated = True
        if self.mode == "lan" and self.net and self.net.role != "host":
            return          # 联机时由主机估算并同步给对方
        moves = list(self.ctrl.moves)
        size = self.size

        def work():
            if self.mode == "puzzle" or self.rule != RULE_TERRITORY:
                return set()
            try:
                eng = self._helper_engine()
                if eng is not None:
                    return eng.dead_stones(size, moves)
            except katago.EngineError:
                pass
            return set()
        self._spawn("dead", work)

    def _on_dead(self, dead, err) -> None:
        if self.ctrl.phase != PHASE_SCORING:
            return
        if dead:
            self.ctrl.set_dead(dead)
            if self.mode == "lan" and self.net:
                self.net.send({"type": "dead_set", "points": [list(p) for p in self.ctrl.dead]})

    # ---------- 输入 ----------
    def handle(self, event: pygame.event.Event) -> None:
        if self.end_dialog:
            for b in self.end_dialog["buttons"]:
                b.handle(event)
            return
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.view.pos_to_cell(*event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_click(event.pos)

    def _on_click(self, pos) -> None:
        cell = self.view.pos_to_cell(*pos)
        if cell is None or self.end_dialog:
            return
        if self.ctrl.phase == PHASE_SCORING:
            if self.busy.get("dead"):
                return
            if self.ctrl.toggle_dead(cell):
                self.app.sound.play("select")
                if self.mode == "lan" and self.net:
                    self.net.send({"type": "dead_toggle", "point": list(cell)})
            return
        if not self._idle() or self.ctrl.phase != PHASE_PLAY or not self._my_turn():
            return
        if not self.ctrl.is_legal(cell):
            if self.ctrl.board.at(cell) is None:
                ko = self.ctrl.board.ko == cell
                self._flash("打劫！要先在别处下一手才能提回" if ko else "这里不能下（没有气的禁着点）")
            return
        self._apply_move(cell, local=True)

    # ---------- 落子 ----------
    def _apply_move(self, move: Move, local: bool) -> None:
        color = self.ctrl.turn
        try:
            captured = self.ctrl.play(move)
        except IllegalMove:
            return
        self.hint_point = None
        if move is None:
            self._flash(f"{color_name(color)}停一手")
        else:
            self.app.sound.play("capture" if captured else "move")
            self.fresh = [move, 0.0]
        self._pending_check = True
        if local and self.mode == "lan" and self.net:
            self.net.send_move(move)
        if self.ctrl.phase != PHASE_SCORING:
            self._dead_estimated = False

    def _after_move(self) -> None:
        """落子动画结束后：判断叫吃提醒、练习题输赢、对局结束。"""
        ctrl = self.ctrl
        if self.mode == "puzzle" and ctrl.phase == PHASE_PLAY:
            black_moves = sum(1 for c, _m in ctrl.moves if c == BLACK)
            if self.puzzle.solved(ctrl.board):
                ctrl._finish(BLACK, "成功吃掉目标！")
            elif ctrl.turn == BLACK and self.puzzle.escaped(ctrl.board, black_moves):
                ctrl._finish(WHITE, "白棋逃掉啦")
        if ctrl.over:
            self._on_game_over()
            return
        mv = ctrl.last_move
        if mv is not None and ctrl.phase == PHASE_PLAY:
            opp = other(ctrl.last_color)
            for nr, nc in ctrl.board.neighbors(*mv):
                if ctrl.board.grid[nr][nc] == opp and ctrl.board.liberty_count(nr, nc) == 1:
                    self.app.sound.play("check")
                    self._flash("叫吃！", 1.2)
                    break
        if ctrl.phase == PHASE_SCORING:
            self.app.sound.play("button")
            self._flash("双方都停一手，开始数子", 3)

    def _on_game_over(self) -> None:
        won = self._human_won()
        if self.ctrl.winner == "draw":
            self.app.sound.play("button")
        else:
            self.app.sound.play("win" if won else "lose")
        self._open_end_dialog()

    def _human_won(self) -> bool:
        if self.mode == "pvp":
            return True
        return self.ctrl.winner == self.human_color

    # ---------- 更新 ----------
    def update(self, dt: float) -> None:
        self._drain_results()
        if self.ctrl.phase != self._buttons_phase:
            self._build_buttons()
        if self.hint_timer > 0:
            self.hint_timer -= dt
            if self.hint_timer <= 0:
                self.hint_point = None
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""
        if self.fresh:
            self.fresh[1] += dt / FRESH_DUR
            if self.fresh[1] >= 1.0:
                self.fresh = None
        if self._pending_check and not self.fresh:
            self._pending_check = False
            self._after_move()
        if self.end_dialog or self.fresh:
            return
        if self.mode == "lan" and self.net:
            self._poll_net()
        if self.ctrl.phase == PHASE_SCORING and not self._dead_estimated:
            self._estimate_dead()
        # 电脑走子
        if self.mode in ("pve", "puzzle") and self.ctrl.phase == PHASE_PLAY \
                and self.ctrl.turn == self.ai_color and not self.busy.get("ai"):
            if self.engine_state == "starting":
                return
            self._ai_wait += dt
            if self._ai_wait >= AI_MIN_DELAY:
                self._ai_wait = 0.0
                self._start_ai()

    def _start_ai(self) -> None:
        board = self.ctrl.board.clone()
        color = self.ai_color
        moves = list(self.ctrl.moves)
        n_moves = len(moves)
        if self.mode == "puzzle":
            from ...game.puzzles import defender_move
            puzzle = self.puzzle
            self._spawn("ai", lambda: (n_moves, defender_move(puzzle, board)))
            return
        eng = self.engine if self.engine_state == "ready" else None
        ai = self.ai

        def work():
            if eng is not None:
                try:
                    return n_moves, eng.genmove(self.size, moves, color)
                except katago.EngineError as e:
                    return n_moves, ("fallback", str(e))
            return n_moves, ai.choose(board, color)
        self._spawn("ai", work)

    def _on_ai(self, value, err) -> None:
        if err is not None or value is None:
            self._flash("电脑出错了，换内置 AI")
            self.engine, self.engine_state = None, "failed"
            return
        n_moves, mv = value
        if n_moves != len(self.ctrl.moves) or self.ctrl.phase != PHASE_PLAY \
                or self.ctrl.turn != self.ai_color:
            return      # 期间悔棋/重开了，丢弃过期结果
        if isinstance(mv, tuple) and len(mv) == 2 and mv[0] == "fallback":
            self.engine, self.engine_state = None, "failed"
            self.engine_note = "KataGo 出错，改用内置 AI"
            return      # 下一帧会用内置 AI 重新思考
        if mv == "resign":
            self.ctrl.resign(self.ai_color)
            self._on_game_over()
            return
        if mv is not None and not self.ctrl.board.is_legal(mv[0], mv[1]):
            mv = self.ai.choose(self.ctrl.board, self.ai_color) if self.mode == "pve" else None
        self._apply_move(mv, local=False)

    def _poll_net(self) -> None:
        for msg in self.net.poll():
            t = msg.get("type")
            if t == "move" and self.ctrl.turn != self.human_color and self.ctrl.phase == PHASE_PLAY:
                p = msg.get("move")
                move = None if not p else (p[0], p[1])
                if move is None or self.ctrl.board.is_legal(*move):
                    self._apply_move(move, local=False)
            elif t == "resign":
                self.ctrl.resign(other(self.human_color))
                self._on_game_over()
            elif t == "dead_toggle" and self.ctrl.phase == PHASE_SCORING:
                self.ctrl.toggle_dead(tuple(msg["point"]))
            elif t == "dead_set" and self.ctrl.phase == PHASE_SCORING:
                self.ctrl.set_dead({tuple(p) for p in msg.get("points", [])})
            elif t == "score_confirm":
                self._confirm_score(from_net=True)
            elif t == "score_resume":
                self._resume_play(from_net=True)
        if self.net.status in ("closed", "error") and not self.ctrl.over and not self.end_dialog:
            self.message = "对手已断开连接"
            self.message_timer = 0

    def _flash(self, text: str, secs: float = 2.5) -> None:
        self.message = text
        self.message_timer = secs

    # ---------- 结束对话框 ----------
    def _open_end_dialog(self) -> None:
        if self.end_dialog:
            return
        if not self._saved and len(self.ctrl.record.moves) > 0:
            save_record(self.ctrl.record)
            self._saved = True
        award = None
        s = self.app.settings
        if self.mode == "pve" and not self._awarded:
            self._awarded = True
            draw = self.ctrl.winner == "draw"
            won = self.ctrl.winner == self.human_color
            award = rank.award(s, won, max(0, self.difficulty), draw=draw)
            self.app.save()
        elif self.mode == "puzzle" and self.ctrl.winner == BLACK and not self._awarded:
            self._awarded = True
            done = s.setdefault("puzzles_done", [])
            if self.puzzle.name not in done:
                done.append(self.puzzle.name)
            award = rank.award(s, True, 1)
            self.app.save()
        ox, oy, ow, oh = theme.WIDTH // 2 - 230, 190, 460, 320
        rect = pygame.Rect(ox, oy, ow, oh)
        first = ("返回菜单", self._to_menu) if self.mode == "lan" else \
            ("再试一次" if self.mode == "puzzle" and self.ctrl.winner != BLACK else "再来一局",
             self._restart)
        btns = [
            Button((ox + 50, oy + oh - 74, 160, 50), first[0], first[1], font_size=22),
            Button((ox + ow - 210, oy + oh - 74, 160, 50), "返回菜单",
                   self._to_menu, font_size=22, color=GREY),
        ]
        if self.mode == "puzzle" and self.ctrl.winner == BLACK and \
                (self.puzzle_index or 0) + 1 < len(self._all_puzzles()):
            btns[0] = Button((ox + 50, oy + oh - 74, 160, 50), "下一关", self._next_puzzle,
                             font_size=22)
        self.end_dialog = {"rect": rect, "buttons": btns, "award": award}

    def _all_puzzles(self):
        from ...game.puzzles import clean_puzzles
        return clean_puzzles()

    def _next_puzzle(self) -> None:
        self.app.sound.play("button")
        self.app.go(GameScene(self.app, mode="puzzle", puzzle_index=(self.puzzle_index or 0) + 1))

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface) -> None:
        ctrl = self.ctrl
        owner = None
        if ctrl.phase == PHASE_SCORING or (ctrl.over and ctrl.rule == RULE_TERRITORY
                                           and "目" in ctrl.result_detail):
            owner = ctrl.score_preview()[4]
        hover_color = None
        if self.hover and ctrl.phase == PHASE_PLAY and self._idle() and self._my_turn() \
                and ctrl.is_legal(self.hover):
            hover_color = ctrl.turn
        atari = []
        if ctrl.phase == PHASE_PLAY:
            for color in (BLACK, WHITE):
                for st, libs in ctrl.board.groups_of(color):
                    if len(libs) == 1:
                        atari.extend(st)
        target = self.puzzle.target if self.mode == "puzzle" else None
        self.view.draw(surf, ctrl.board, last_move=ctrl.last_move,
                       hover=self.hover, hover_color=hover_color,
                       dead=ctrl.dead, owner=owner, hint=self.hint_point,
                       target=target, atari=atari,
                       fresh=tuple(self.fresh) if self.fresh else None)
        self._draw_panel(surf)
        for b in self.buttons:
            b.draw(surf)
        if self.end_dialog:
            self._draw_end_dialog(surf)

    def _draw_panel(self, surf: pygame.Surface) -> None:
        panel = pygame.Rect(theme.PANEL_X, 0, theme.WIDTH - theme.PANEL_X, theme.HEIGHT)
        pygame.draw.rect(surf, theme.PANEL_BG, panel)
        pygame.draw.line(surf, theme.PANEL_LINE, (theme.PANEL_X, 0), (theme.PANEL_X, theme.HEIGHT), 2)
        x = theme.PANEL_X + 24
        maxw = theme.WIDTH - theme.PANEL_X - 48
        dim = theme.get_font(18)
        titles = {"pve": "人机对战", "pvp": "双人对战", "lan": "局域网联机", "puzzle": "吃子练习"}
        surf.blit(theme.get_font(30, bold=True).render(titles.get(self.mode, ""), True, theme.RED),
                  (x, 20))
        y = 60
        if self.mode == "puzzle":
            sub = self.puzzle.name
        elif self.rule == RULE_CAPTURE:
            sub = f"吃子棋 · {self.size} 路 · 先吃 {self.capture_target} 子获胜"
        else:
            sub = f"正式对局 · {self.size} 路 · 黑贴 {KOMI:g} 目"
        surf.blit(dim.render(sub, True, theme.TEXT_DIM), (x, y))
        y += 24
        extra = ""
        if self.mode == "pve":
            extra = f"难度：{DIFFICULTIES[max(0, self.difficulty)][0]}　你执{'黑' if self.human_color == BLACK else '白'}"
        elif self.mode == "lan":
            extra = f"你执{'黑' if self.human_color == BLACK else '白'}棋"
        if extra:
            surf.blit(dim.render(extra, True, theme.TEXT_DIM), (x, y))
            y += 24
        if self.mode == "pve" and self.rule == RULE_TERRITORY:
            if self.engine_state == "starting":
                note, col = "KataGo 引擎加载中…（首次可能要一两分钟）", theme.ATARI
            elif self.engine_state == "ready":
                note, col = self.engine_note, theme.SELECT
            elif self.engine_note:
                note, col = self.engine_note, theme.ATARI
            else:
                note, col = "电脑：内置 AI（未装 KataGo）", theme.TEXT_DIM
            y = self._draw_wrapped(surf, note, x, y, maxw, theme.get_font(16), col)
        y += 6
        self._draw_turn(surf, x, y)
        y += 34
        caps = self.ctrl.board.captures
        cap_txt = f"黑提 {caps[BLACK]} 子　　白提 {caps[WHITE]} 子"
        surf.blit(theme.get_font(19, bold=True).render(cap_txt, True, theme.TEXT), (x, y))
        y += 30
        if self.mode == "puzzle":
            used = sum(1 for c, _m in self.ctrl.moves if c == BLACK)
            y = self._draw_wrapped(surf, self.puzzle.tip, x, y, maxw, theme.get_font(17),
                                   theme.TEXT_DIM)
            surf.blit(dim.render(f"已下 {used} / 最多 {self.puzzle.max_moves} 手", True, theme.TEXT),
                      (x, y + 2))
            y += 30
        if self.ctrl.phase == PHASE_SCORING:
            y = self._draw_scoring(surf, x, y, maxw)
        self._draw_moves(surf, x, y + 4)
        if self.message:
            m = theme.get_font(19, bold=True).render(self.message, True, theme.CHECK)
            surf.blit(m, (x, self._list_bottom + 8))

    def _draw_turn(self, surf, x, y) -> None:
        if self.ctrl.over:
            txt, col = "对局结束", theme.TEXT
            pygame.draw.circle(surf, col, (x + 10, y + 12), 9)
        elif self.ctrl.phase == PHASE_SCORING:
            txt, col = "数子中", theme.TEXT
            pygame.draw.circle(surf, theme.GOLD, (x + 10, y + 12), 9)
        else:
            turn = self.ctrl.turn
            if turn == BLACK:
                pygame.draw.circle(surf, theme.BLACK_STONE, (x + 10, y + 12), 10)
            else:
                pygame.draw.circle(surf, theme.WHITE_STONE, (x + 10, y + 12), 10)
                pygame.draw.circle(surf, theme.WHITE_STONE_EDGE, (x + 10, y + 12), 10, 1)
            col = theme.TEXT
            extra = ""
            if self.busy.get("ai") or (self.mode in ("pve", "puzzle") and turn == self.ai_color):
                extra = "（电脑思考中…）"
            elif self.mode == "lan" and turn != self.human_color:
                extra = "（等待对方）"
            txt = f"轮到 {'黑棋' if turn == BLACK else '白棋'} 下{extra}"
        surf.blit(theme.get_font(21, bold=True).render(txt, True, col), (x + 28, y))

    def _draw_scoring(self, surf, x, y, maxw) -> int:
        winner, margin, b, w, _o = self.ctrl.score_preview()
        f = theme.get_font(18)
        if self.busy.get("dead"):
            surf.blit(f.render("正在判断死子…", True, theme.ATARI), (x, y))
            y += 24
        lines = [
            f"黑 {b} 子　白 {w} 子（+ 贴 {KOMI:g}）",
            f"预计：{'黑' if winner == BLACK else '白'}胜 {margin:g} 目",
        ]
        for line in lines:
            surf.blit(theme.get_font(19, bold=True).render(line, True, theme.TEXT), (x, y))
            y += 26
        y = self._draw_wrapped(surf, "点击棋盘上的棋子，可以把整块标成死子（打叉）或取消。小方块表示这个点归谁。",
                               x, y + 2, maxw, theme.get_font(16), theme.TEXT_DIM)
        return y + 6

    def _draw_wrapped(self, surf, text, x, y, maxw, font, color) -> int:
        line = ""
        for ch in text:
            if font.size(line + ch)[0] > maxw:
                surf.blit(font.render(line, True, color), (x, y))
                y += font.get_height() + 2
                line = ch
            else:
                line += ch
        if line:
            surf.blit(font.render(line, True, color), (x, y))
            y += font.get_height() + 2
        return y

    def _draw_moves(self, surf, x, y) -> None:
        font = theme.get_font(17)
        surf.blit(theme.get_font(19, bold=True).render("着法记录", True, theme.TEXT), (x, y))
        y += 28
        notes = self.ctrl.record.notations
        line_h = 24
        rows = max(0, (self._list_bottom - y) // line_h)
        if rows == 0:
            return
        # 每行两手：第 n 手 + 第 n+1 手
        pairs = []
        for i in range(0, len(notes), 2):
            pairs.append((i + 1, notes[i], notes[i + 1] if i + 1 < len(notes) else ""))
        for no, a, b in pairs[-rows:]:
            surf.blit(font.render(f"{no:>3}.", True, theme.TEXT_DIM), (x, y))
            surf.blit(font.render(a, True, theme.TEXT), (x + 44, y))
            surf.blit(font.render(b, True, theme.TEXT), (x + 160, y))
            y += line_h

    def _draw_end_dialog(self, surf) -> None:
        theme.draw_veil(surf, 140)
        r = self.end_dialog["rect"]
        pygame.draw.rect(surf, theme.PANEL_BG, r, border_radius=20)
        pygame.draw.rect(surf, theme.GOLD, r, width=4, border_radius=20)
        winner = self.ctrl.winner
        if winner == "draw":
            title, col = "和棋！", theme.TEXT
        elif self.mode == "puzzle":
            title, col = ("过关啦！", theme.RED) if winner == BLACK else ("差一点点！", theme.BLACK_STONE)
        elif self.mode == "pvp":
            title = ("黑棋" if winner == BLACK else "白棋") + " 获胜！"
            col = theme.BLACK_STONE
        elif self._human_won():
            title, col = "恭喜你赢啦！", theme.RED
        else:
            title, col = "再接再厉！", theme.BLACK_STONE
        t = theme.get_font(38, bold=True).render(title, True, col)
        surf.blit(t, t.get_rect(center=(r.centerx, r.y + 56)))
        y = r.y + 108
        if winner in (BLACK, WHITE):
            detail = f"{'黑' if winner == BLACK else '白'}方{self.ctrl.result_detail}" \
                if self.mode != "puzzle" else self.ctrl.result_detail
        else:
            detail = self.ctrl.result_detail
        d = theme.get_font(22).render(detail, True, theme.TEXT)
        surf.blit(d, d.get_rect(center=(r.centerx, y)))
        y += 40
        award = self.end_dialog.get("award")
        if award:
            dlt = award["delta"]
            sign = "+" if dlt >= 0 else ""
            info = theme.get_font(20).render(f"积分 {sign}{dlt}　当前 {award['score']} 分",
                                             True, theme.TEXT_DIM)
            surf.blit(info, info.get_rect(center=(r.centerx, y)))
            y += 36
            if award["promoted"]:
                p = theme.get_font(24, bold=True).render(f"晋级：{award['rank_name']}！", True, theme.GOLD)
                surf.blit(p, p.get_rect(center=(r.centerx, y)))
        for b in self.end_dialog["buttons"]:
            b.draw(surf)
