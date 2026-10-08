"""主菜单：显示玩家段位成长，进入各种对局模式。"""
from __future__ import annotations

import pygame

from .. import theme
from ..app import Scene
from ..widgets import Button, Segmented, TextInput
from ...engine import katago
from ...engine.ai import DIFFICULTIES, RULE_CAPTURE, RULE_TERRITORY
from ...engine.stones import BLACK, SIZES, WHITE
from ...game import rank

RULES = [RULE_CAPTURE, RULE_TERRITORY]
TARGETS = [1, 3, 5]
GREY = (150, 120, 90)


class MenuScene(Scene):
    def on_enter(self) -> None:
        self.overlay = None          # None / 'pve' / 'pvp' / 'puzzle' / 'name'
        self.buttons = []
        self.overlay_widgets = []
        self._build_main()

    # ---------- 主菜单按钮 ----------
    def _build_main(self) -> None:
        self.buttons = []
        bx = theme.WIDTH - 360
        bw, bh, gap = 300, 62, 20
        top = 140
        items = [
            ("人机对战", lambda: self._open("pve")),
            ("双人对战", lambda: self._open("pvp")),
            ("吃子练习", lambda: self._open("puzzle")),
            ("局域网联机", self._open_lan),
            ("棋谱记录", self._open_records),
        ]
        for i, (label, cb) in enumerate(items):
            self.buttons.append(Button((bx, top + i * (bh + gap), bw, bh), label,
                                       cb, font_size=26))
        by = theme.HEIGHT - 90
        sw = (bw - 16) // 3
        self.buttons.append(Button((bx, by, sw, 50), self._sound_label(),
                                   self._toggle_sound, font_size=18, color=GREY))
        self.buttons.append(Button((bx + sw + 8, by, sw, 50), "改名字",
                                   lambda: self._open("name"), font_size=18, color=GREY))
        self.buttons.append(Button((bx + (sw + 8) * 2, by, sw, 50), "AI 引擎",
                                   self._open_engine, font_size=18, color=GREY))

    def _sound_label(self) -> str:
        return "音效：开" if self.app.settings.get("sound", True) else "音效：关"

    # ---------- 动作 ----------
    def _toggle_sound(self) -> None:
        on = not self.app.settings.get("sound", True)
        self.app.settings["sound"] = on
        self.app.sound.set_enabled(on)
        self.app.save()
        self.app.sound.play("button")
        self._build_main()

    def _open(self, name: str) -> None:
        self.app.sound.play("button")
        self.overlay = name
        self.overlay_widgets = []
        if name in ("pve", "pvp"):
            self._build_game_overlay(name)
        elif name == "puzzle":
            self._build_puzzle_overlay()
        elif name == "name":
            self._build_name_overlay()

    def _close_overlay(self) -> None:
        self.overlay = None
        self.overlay_widgets = []

    def _open_lan(self) -> None:
        self.app.sound.play("button")
        from .lan import LanScene
        self.app.go(LanScene(self.app))

    def _open_records(self) -> None:
        self.app.sound.play("button")
        from .records import RecordsScene
        self.app.go(RecordsScene(self.app))

    def _open_engine(self) -> None:
        self.app.sound.play("button")
        from .engine import EngineScene
        self.app.go(EngineScene(self.app))

    # ---------- 对局选项（人机 / 双人）----------
    def _build_game_overlay(self, kind: str) -> None:
        s = self.app.settings
        self._color = BLACK
        self._engine_ok = katago.is_available(s)
        self._has_human = bool(katago.engine_status(s)["human_model"]) if self._engine_ok else False
        ox, oy, ow, oh = theme.WIDTH // 2 - 290, 70, 580, 580
        self._overlay_rect = pygame.Rect(ox, oy, ow, oh)
        x = ox + 40
        rule_idx = RULES.index(s.get("rule", RULE_CAPTURE)) if s.get("rule") in RULES else 0
        size_idx = SIZES.index(s.get("board_size", 9)) if s.get("board_size") in SIZES else 0
        tgt_idx = TARGETS.index(s.get("capture_target", 3)) if s.get("capture_target") in TARGETS else 1
        self._rule = Segmented(x, oy + 76, "玩法", ["吃子棋", "正式对局"], rule_idx,
                               self._on_rule, seg_w=150)
        self._size = Segmented(x, oy + 128, "棋盘", ["9 路", "13 路", "19 路"], size_idx,
                               lambda i: self._save_opt("board_size", SIZES[i]), seg_w=110)
        self._target = Segmented(x, oy + 180, "吃几子", ["先吃 1 子", "先吃 3 子", "先吃 5 子"],
                                 tgt_idx, lambda i: self._save_opt("capture_target", TARGETS[i]),
                                 seg_w=110)
        w = self.overlay_widgets
        w += [self._rule, self._size, self._target]
        if kind == "pve":
            self._color_seg = Segmented(x, oy + 232, "我执", ["黑棋（先下）", "白棋（后下）"], 0,
                                        self._on_color, seg_w=150)
            w.append(self._color_seg)
            half = (ow - 80 - 16) // 2
            self._level_buttons = []
            for i in range(len(DIFFICULTIES)):
                col, row = i % 2, i // 2
                btn = Button((x + col * (half + 16), oy + 330 + row * 54, half, 46), "",
                             lambda i=i: self._start_pve(i), font_size=21)
                self._level_buttons.append(btn)
                w.append(btn)
            self._refresh_level_labels()
        else:
            w.append(Button((ox + ow // 2 - 110, oy + 300, 220, 54), "开始对局",
                            self._start_pvp, font_size=24))
        w.append(Button((ox + ow - 40 - 140, oy + oh - 66, 140, 46), "返回",
                        self._close_overlay, font_size=20, color=GREY))
        self._on_rule(rule_idx, save=False)

    def _on_rule(self, i: int, save: bool = True) -> None:
        self._target.visible = RULES[i] == RULE_CAPTURE
        if save:
            self._save_opt("rule", RULES[i])
        if self.overlay == "pve":
            self._refresh_level_labels()

    def _on_color(self, i: int) -> None:
        self._color = BLACK if i == 0 else WHITE

    def _save_opt(self, key: str, value) -> None:
        self.app.settings[key] = value
        self.app.save()

    def _uses_katago(self) -> bool:
        return RULES[self._rule.selected] == RULE_TERRITORY and self._engine_ok

    def _refresh_level_labels(self) -> None:
        for i, btn in enumerate(getattr(self, "_level_buttons", [])):
            name = DIFFICULTIES[i][0]
            if self._uses_katago() and self._has_human:
                btn.label = f"{name}（约 {katago.LEVEL_RANK_CN[i]}）"
            else:
                btn.label = f"{name}（第 {i + 1} 级）"

    def _game_opts(self) -> dict:
        return {
            "rule": RULES[self._rule.selected],
            "size": SIZES[self._size.selected],
            "capture_target": TARGETS[self._target.selected],
        }

    def _start_pve(self, difficulty: int) -> None:
        self.app.sound.play("button")
        self.app.settings["difficulty"] = difficulty
        self.app.save()
        from .game import GameScene
        self.app.go(GameScene(self.app, mode="pve", difficulty=difficulty,
                              human_color=self._color, **self._game_opts()))

    def _start_pvp(self) -> None:
        self.app.sound.play("button")
        from .game import GameScene
        self.app.go(GameScene(self.app, mode="pvp", **self._game_opts()))

    # ---------- 练习题选择 ----------
    def _build_puzzle_overlay(self) -> None:
        from ...game.puzzles import clean_puzzles
        self._puzzles = clean_puzzles()
        ox, oy, ow = theme.WIDTH // 2 - 260, 110, 520
        oh = 150 + len(self._puzzles) * 60
        self._overlay_rect = pygame.Rect(ox, oy, ow, oh)
        done = set(self.app.settings.get("puzzles_done", []))
        for i, p in enumerate(self._puzzles):
            y = oy + 84 + i * 60
            label = ("★ " if p.name in done else "") + p.name
            self.overlay_widgets.append(
                Button((ox + 40, y, ow - 80, 50), label,
                       lambda i=i: self._start_puzzle(i), font_size=22))
        self.overlay_widgets.append(
            Button((ox + ow // 2 - 70, oy + oh - 62, 140, 44), "返回",
                   self._close_overlay, font_size=20, color=GREY))

    def _start_puzzle(self, idx: int) -> None:
        self.app.sound.play("button")
        from .game import GameScene
        self.app.go(GameScene(self.app, mode="puzzle", puzzle_index=idx))

    # ---------- 改名字 ----------
    def _build_name_overlay(self) -> None:
        ox, oy, ow, oh = theme.WIDTH // 2 - 220, 220, 440, 240
        self._overlay_rect = pygame.Rect(ox, oy, ow, oh)
        self._name_input = TextInput((ox + 60, oy + 100, ow - 120, 48),
                                     text=self.app.settings.get("player_name", "小棋手"),
                                     placeholder="输入你的名字", max_len=8, font_size=24)
        self._name_input.focused = True
        self.overlay_widgets = [
            self._name_input,
            Button((ox + 60, oy + oh - 66, 130, 46), "保存", self._save_name, font_size=22),
            Button((ox + ow - 190, oy + oh - 66, 130, 46), "取消",
                   self._close_overlay, font_size=22, color=GREY),
        ]

    def _save_name(self) -> None:
        name = self._name_input.text.strip() or "小棋手"
        self.app.settings["player_name"] = name
        self.app.save()
        self.app.sound.play("button")
        self._close_overlay()

    # ---------- 事件 ----------
    def handle(self, event: pygame.event.Event) -> None:
        if self.overlay:
            for w in list(self.overlay_widgets):
                w.handle(event)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._close_overlay()
            return
        for b in self.buttons:
            b.handle(event)

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(theme.BG)
        self._draw_decor(surf)
        self._draw_title(surf)
        self._draw_rank_card(surf)
        for b in self.buttons:
            b.draw(surf)
        if self.overlay:
            self._draw_overlay(surf)

    def _draw_decor(self, surf: pygame.Surface) -> None:
        # 左下角一小块棋盘 + 黑白子装饰
        ox, oy, cell, n = 70, theme.HEIGHT - 290, 46, 6
        rect = pygame.Rect(ox - 26, oy - 26, cell * (n - 1) + 52, cell * (n - 1) + 52)
        pygame.draw.rect(surf, theme.BOARD_BG, rect, border_radius=10)
        pygame.draw.rect(surf, theme.LINE, rect, width=2, border_radius=10)
        for i in range(n):
            pygame.draw.line(surf, theme.LINE, (ox, oy + i * cell), (ox + (n - 1) * cell, oy + i * cell), 1)
            pygame.draw.line(surf, theme.LINE, (ox + i * cell, oy), (ox + i * cell, oy + (n - 1) * cell), 1)
        stones = [(1, 2, BLACK), (2, 3, BLACK), (2, 2, WHITE), (3, 2, BLACK), (2, 1, WHITE),
                  (3, 3, WHITE), (1, 3, WHITE), (4, 2, WHITE), (3, 1, BLACK)]
        for r, c, col in stones:
            x, y = ox + c * cell, oy + r * cell
            pygame.draw.circle(surf, theme.STONE_SHADOW, (x + 2, y + 3), 21)
            if col == BLACK:
                pygame.draw.circle(surf, theme.BLACK_STONE, (x, y), 21)
                pygame.draw.circle(surf, theme.BLACK_STONE_HI, (x - 7, y - 7), 6)
            else:
                pygame.draw.circle(surf, theme.WHITE_STONE, (x, y), 21)
                pygame.draw.circle(surf, theme.WHITE_STONE_EDGE, (x, y), 21, 1)

    def _draw_title(self, surf: pygame.Surface) -> None:
        f = theme.get_font(64, bold=True)
        shadow = f.render("围  棋", True, (120, 80, 40))
        surf.blit(shadow, (63, 43))
        t = f.render("围  棋", True, theme.BLACK_STONE)
        surf.blit(t, (60, 40))
        sub = theme.get_font(26).render("少儿版 · 黑白之间，快乐成长", True, theme.TEXT_DIM)
        surf.blit(sub, (64, 116))

    def _draw_rank_card(self, surf: pygame.Surface) -> None:
        s = self.app.settings
        score = s.get("rank_score", 0)
        _idx, name = rank.rank_of(score)
        nxt_name, need = rank.next_rank(score)
        card = pygame.Rect(60, 170, 440, 180)
        pygame.draw.rect(surf, theme.PANEL_BG, card, border_radius=16)
        pygame.draw.rect(surf, theme.GOLD, card, width=3, border_radius=16)
        pn = theme.get_font(28, bold=True).render(s.get("player_name", "小棋手"), True, theme.TEXT)
        surf.blit(pn, (card.x + 24, card.y + 20))
        rk = theme.get_font(30, bold=True).render(f"★ {name}", True, theme.GOLD)
        surf.blit(rk, (card.x + 24, card.y + 60))
        bar = pygame.Rect(card.x + 24, card.y + 108, card.width - 48, 18)
        pygame.draw.rect(surf, (225, 214, 194), bar, border_radius=9)
        p = rank.progress(score)
        fill = pygame.Rect(bar.x, bar.y, int(bar.width * p), bar.height)
        pygame.draw.rect(surf, theme.GOLD, fill, border_radius=9)
        if nxt_name:
            tip = f"积分 {score}　距【{nxt_name}】还差 {need} 分"
        else:
            tip = f"积分 {score}　已达最高段位！"
        surf.blit(theme.get_font(18).render(tip, True, theme.TEXT_DIM), (card.x + 24, card.y + 132))
        rec = f"胜 {s.get('wins', 0)}　负 {s.get('losses', 0)}　和 {s.get('draws', 0)}"
        surf.blit(theme.get_font(18).render(rec, True, theme.TEXT_DIM), (card.x + 24, card.y + 154))

    def _draw_overlay(self, surf: pygame.Surface) -> None:
        theme.draw_veil(surf, 130)
        r = self._overlay_rect
        pygame.draw.rect(surf, theme.PANEL_BG, r, border_radius=18)
        pygame.draw.rect(surf, theme.GOLD, r, width=3, border_radius=18)
        titles = {"pve": "人机对战", "pvp": "双人对战", "puzzle": "吃子练习 · 选择关卡",
                  "name": "修改名字"}
        t = theme.get_font(30, bold=True).render(titles.get(self.overlay, ""), True, theme.TEXT)
        surf.blit(t, t.get_rect(center=(r.centerx, r.y + 38)))
        if self.overlay == "pve":
            if RULES[self._rule.selected] == RULE_CAPTURE:
                info = "吃子棋由内置 AI 陪你下"
                col = theme.TEXT_DIM
            elif self._engine_ok:
                info = "电脑：KataGo" + ("（人类风格，按级位模仿）" if self._has_human else "（按搜索量分档）")
                col = theme.SELECT
            else:
                info = "未检测到 KataGo，使用内置 AI（较弱）。可在主菜单「AI 引擎」里设置"
                col = theme.ATARI
            h = theme.get_font(17).render(info, True, col)
            surf.blit(h, h.get_rect(center=(r.centerx, r.y + 300)))
        elif self.overlay == "pvp":
            h = theme.get_font(17).render("两个人在同一台电脑上轮流下", True, theme.TEXT_DIM)
            surf.blit(h, h.get_rect(center=(r.centerx, r.y + 380)))
        for w in self.overlay_widgets:
            w.draw(surf)
