"""棋谱记录管理：列出、回放、删除已保存的对局。"""
from __future__ import annotations

import pygame

from .. import theme
from ..app import Scene
from ..widgets import Button
from ...game.record import list_records, delete_record

ROW_H = 58


class RecordsScene(Scene):
    def on_enter(self) -> None:
        self.refresh()
        self.scroll = 0
        self.confirm_delete = None  # (path, rect)
        self.back_btn = Button((40, theme.HEIGHT - 74, 160, 50), "返回菜单",
                               self._to_menu, font_size=22, color=(150, 120, 90))

    def refresh(self) -> None:
        self.records = list_records()   # [(path, rec)]

    def _to_menu(self) -> None:
        self.app.sound.play("button")
        from .menu import MenuScene
        self.app.go(MenuScene(self.app))

    # ---------- 列表几何 ----------
    @property
    def _list_rect(self) -> pygame.Rect:
        return pygame.Rect(40, 110, theme.WIDTH - 80, theme.HEIGHT - 200)

    def _row_rects(self):
        lr = self._list_rect
        for i, (path, rec) in enumerate(self.records):
            y = lr.y + i * ROW_H - self.scroll
            row = pygame.Rect(lr.x, y, lr.width, ROW_H - 8)
            play = pygame.Rect(row.right - 220, row.y + 6, 90, ROW_H - 20)
            dele = pygame.Rect(row.right - 118, row.y + 6, 90, ROW_H - 20)
            yield path, rec, row, play, dele

    # ---------- 事件 ----------
    def handle(self, event: pygame.event.Event) -> None:
        if self.confirm_delete:
            self._handle_confirm(event)
            return
        self.back_btn.handle(event)
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_by(-event.y * 40)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lr = self._list_rect
            for path, rec, row, play, dele in self._row_rects():
                if not lr.colliderect(row):
                    continue
                if play.collidepoint(event.pos):
                    self._replay(path)
                    return
                if dele.collidepoint(event.pos):
                    self.app.sound.play("button")
                    self.confirm_delete = path
                    return

    def _scroll_by(self, dy: int) -> None:
        total = len(self.records) * ROW_H
        max_scroll = max(0, total - self._list_rect.height)
        self.scroll = max(0, min(self.scroll + dy, max_scroll))

    def _replay(self, path) -> None:
        self.app.sound.play("button")
        from .replay import ReplayScene
        self.app.go(ReplayScene(self.app, path))

    def _handle_confirm(self, event) -> None:
        r = pygame.Rect(theme.WIDTH // 2 - 200, theme.HEIGHT // 2 - 90, 400, 180)
        yes = pygame.Rect(r.x + 40, r.bottom - 66, 140, 46)
        no = pygame.Rect(r.right - 180, r.bottom - 66, 140, 46)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if yes.collidepoint(event.pos):
                delete_record(self.confirm_delete)
                self.confirm_delete = None
                self.refresh()
                self.app.sound.play("button")
            elif no.collidepoint(event.pos):
                self.confirm_delete = None
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.confirm_delete = None

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(theme.BG)
        title = theme.get_font(40, bold=True).render("棋谱记录", True, theme.RED)
        surf.blit(title, (40, 40))
        lr = self._list_rect
        pygame.draw.rect(surf, theme.PANEL_BG, lr, border_radius=12)
        pygame.draw.rect(surf, theme.PANEL_LINE, lr, width=2, border_radius=12)
        prev_clip = surf.get_clip()
        surf.set_clip(lr)
        if not self.records:
            tip = theme.get_font(24).render("还没有棋谱，快去下一盘吧！", True, theme.TEXT_DIM)
            surf.blit(tip, tip.get_rect(center=lr.center))
        for path, rec, row, play, dele in self._row_rects():
            if row.bottom < lr.y or row.y > lr.bottom:
                continue
            pygame.draw.rect(surf, (255, 255, 255), row, border_radius=8)
            pygame.draw.rect(surf, theme.PANEL_LINE, row, width=1, border_radius=8)
            t = theme.get_font(19).render(rec.title, True, theme.TEXT)
            surf.blit(t, (row.x + 16, row.centery - t.get_height() // 2))
            self._mini_btn(surf, play, "回放", theme.BTN)
            self._mini_btn(surf, dele, "删除", (170, 80, 70))
        surf.set_clip(prev_clip)
        self.back_btn.draw(surf)
        if self.confirm_delete:
            self._draw_confirm(surf)

    def _mini_btn(self, surf, rect, label, color) -> None:
        pygame.draw.rect(surf, color, rect, border_radius=8)
        t = theme.get_font(18, bold=True).render(label, True, theme.BTN_TEXT)
        surf.blit(t, t.get_rect(center=rect.center))

    def _draw_confirm(self, surf) -> None:
        theme.draw_veil(surf, 140)
        r = pygame.Rect(theme.WIDTH // 2 - 200, theme.HEIGHT // 2 - 90, 400, 180)
        pygame.draw.rect(surf, theme.PANEL_BG, r, border_radius=16)
        pygame.draw.rect(surf, theme.GOLD, r, width=3, border_radius=16)
        t = theme.get_font(24, bold=True).render("确定删除这份棋谱吗？", True, theme.TEXT)
        surf.blit(t, t.get_rect(center=(r.centerx, r.y + 50)))
        self._mini_btn(surf, pygame.Rect(r.x + 40, r.bottom - 66, 140, 46), "删除", (170, 80, 70))
        self._mini_btn(surf, pygame.Rect(r.right - 180, r.bottom - 66, 140, 46), "取消", theme.BTN)
