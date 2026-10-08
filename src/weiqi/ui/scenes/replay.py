"""棋谱回放：前进/后退/自动播放，逐步重现对局；可切换显示手数。"""
from __future__ import annotations

import pygame

from .. import theme
from ..app import Scene
from ..board_view import BoardView
from ..widgets import Button
from ...engine.board import IllegalMove
from ...game.record import GameRecord, load_record

GREY = (150, 120, 90)


class ReplayScene(Scene):
    def __init__(self, app, path):
        super().__init__(app)
        self.path = path

    def on_enter(self) -> None:
        self.record = load_record(self.path)
        self.view = BoardView(self.record.size if self.record else 9)
        self.ply = 0                       # 已走手数
        self.auto = False
        self.auto_timer = 0.0
        self.show_numbers = False
        self.moves = [GameRecord.decode(m) for m in (self.record.moves if self.record else [])]
        self._rebuild()
        self._build_buttons()

    def _rebuild(self) -> None:
        """按 self.ply 重放棋盘，同时记下每个棋子是第几手下的。"""
        if self.record is None:
            from ...engine.board import Board
            self.board = Board(9)
            self.numbers = {}
            return
        self.board = self.record.build_start()
        self.numbers = {}
        for i in range(self.ply):
            self._play(i)

    def _play(self, i: int) -> bool:
        mv = self.moves[i]
        try:
            captured = self.board.play(mv)
        except IllegalMove:
            return False
        for p in captured:
            self.numbers.pop(p, None)
        if mv is not None:
            self.numbers[mv] = i + 1
        return bool(captured)

    def _build_buttons(self) -> None:
        x = theme.PANEL_X + 24
        w = theme.WIDTH - theme.PANEL_X - 48
        half = (w - 16) // 2
        y = theme.HEIGHT - 252
        self.buttons = [
            Button((x, y, half, 46), "|< 开始", lambda: self._goto(0), font_size=20),
            Button((x + half + 16, y, half, 46), "上一步", self._prev, font_size=20),
            Button((x, y + 56, half, 46), "下一步", self._next, font_size=20),
            Button((x + half + 16, y + 56, half, 46), "末尾 >|",
                   lambda: self._goto(len(self.moves)), font_size=20),
            Button((x, y + 112, half, 46), "自动播放", self._toggle_auto, font_size=20,
                   color=theme.GOLD),
            Button((x + half + 16, y + 112, half, 46), "显示手数", self._toggle_numbers,
                   font_size=20, color=GREY),
            Button((x, y + 168, w, 46), "返回", self._back, font_size=20, color=GREY),
        ]

    # ---------- 控制 ----------
    def _goto(self, ply: int) -> None:
        self.ply = max(0, min(ply, len(self.moves)))
        self._rebuild()
        self.app.sound.play("button")

    def _next(self) -> None:
        if self.ply < len(self.moves):
            cap = self._play(self.ply)
            self.ply += 1
            if self.moves[self.ply - 1] is not None:
                self.app.sound.play("capture" if cap else "move")

    def _prev(self) -> None:
        if self.ply > 0:
            self._goto(self.ply - 1)

    def _toggle_auto(self) -> None:
        self.auto = not self.auto
        self.auto_timer = 0.0
        self.buttons[4].label = "暂停" if self.auto else "自动播放"

    def _toggle_numbers(self) -> None:
        self.show_numbers = not self.show_numbers
        self.buttons[5].label = "隐藏手数" if self.show_numbers else "显示手数"

    def _back(self) -> None:
        self.app.sound.play("button")
        from .records import RecordsScene
        self.app.go(RecordsScene(self.app))

    # ---------- 更新 ----------
    def update(self, dt: float) -> None:
        if self.auto:
            self.auto_timer += dt
            if self.auto_timer >= 0.8:
                self.auto_timer = 0.0
                if self.ply < len(self.moves):
                    self._next()
                else:
                    self._toggle_auto()

    def handle(self, event: pygame.event.Event) -> None:
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RIGHT:
                self._next()
            elif event.key == pygame.K_LEFT:
                self._prev()

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface) -> None:
        last = self.moves[self.ply - 1] if self.ply > 0 else None
        self.view.draw(surf, self.board, last_move=last,
                       numbers=self.numbers if self.show_numbers else None)
        self._draw_panel(surf)
        for b in self.buttons:
            b.draw(surf)

    def _draw_panel(self, surf) -> None:
        panel = pygame.Rect(theme.PANEL_X, 0, theme.WIDTH - theme.PANEL_X, theme.HEIGHT)
        pygame.draw.rect(surf, theme.PANEL_BG, panel)
        pygame.draw.line(surf, theme.PANEL_LINE, (theme.PANEL_X, 0), (theme.PANEL_X, theme.HEIGHT), 2)
        x = theme.PANEL_X + 24
        surf.blit(theme.get_font(28, bold=True).render("棋谱回放", True, theme.RED), (x, 22))
        if self.record is None:
            surf.blit(theme.get_font(20).render("棋谱读取失败", True, theme.CHECK), (x, 70))
            return
        rec = self.record
        f = theme.get_font(18)
        surf.blit(f.render(f"{rec.black_name}（黑） vs {rec.white_name}（白）", True, theme.TEXT),
                  (x, 62))
        if rec.result in ("b", "w"):
            res = f"{'黑' if rec.result == 'b' else '白'}方{rec.result_detail or '胜'}"
        else:
            res = "和棋" if rec.result == "draw" else "未下完"
        surf.blit(f.render(res, True, theme.TEXT_DIM), (x, 86))
        surf.blit(f.render(f"第 {self.ply} / {len(self.moves)} 手　黑提 {self.board.captures['b']}　"
                           f"白提 {self.board.captures['w']}", True, theme.TEXT_DIM), (x, 110))
        # 着法列表（高亮当前）
        font = theme.get_font(17)
        y = 146
        notes = rec.notations
        line_h = 24
        bottom = theme.HEIGHT - 264
        rows = (bottom - y) // line_h
        cur_pair = (self.ply - 1) // 2 if self.ply > 0 else -1
        pairs = [(i // 2, i + 1, notes[i], notes[i + 1] if i + 1 < len(notes) else "")
                 for i in range(0, len(notes), 2)]
        start = max(0, cur_pair - rows + 3)
        for idx, no, a, b in pairs[start:start + rows]:
            color = theme.RED if idx == cur_pair else theme.TEXT
            surf.blit(font.render(f"{no:>3}.", True, theme.TEXT_DIM), (x, y))
            surf.blit(font.render(a, True, color), (x + 44, y))
            surf.blit(font.render(b, True, color), (x + 160, y))
            y += line_h
