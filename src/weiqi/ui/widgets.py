"""通用 UI 控件：按钮、文本输入框、单选按钮组。"""
from __future__ import annotations

from typing import Callable, Optional

import pygame

from . import theme


class Button:
    def __init__(self, rect, label: str, on_click: Optional[Callable] = None,
                 font_size: int = 24, color=theme.BTN, text_color=theme.BTN_TEXT):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.font_size = font_size
        self.color = color
        self.text_color = text_color
        self.enabled = True
        self.hover = False

    def handle(self, event: pygame.event.Event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surf: pygame.Surface) -> None:
        if not self.enabled:
            color = theme.BTN_DISABLED
        elif self.hover:
            color = theme.BTN_HOVER
        else:
            color = self.color
        shadow = self.rect.move(0, 3)
        pygame.draw.rect(surf, (0, 0, 0, 40), shadow, border_radius=12)
        pygame.draw.rect(surf, color, self.rect, border_radius=12)
        pygame.draw.rect(surf, theme.GOLD, self.rect, width=2, border_radius=12)
        font = theme.get_font(self.font_size, bold=True)
        txt = font.render(self.label, True, self.text_color if self.enabled else theme.TEXT_DIM)
        surf.blit(txt, txt.get_rect(center=self.rect.center))


class TextInput:
    def __init__(self, rect, text: str = "", placeholder: str = "",
                 max_len: int = 20, font_size: int = 24, numeric_dot: bool = False):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.placeholder = placeholder
        self.max_len = max_len
        self.font_size = font_size
        self.focused = False
        self.numeric_dot = numeric_dot  # 仅允许数字和点（用于 IP）

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.focused:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                self.focused = False
            elif event.unicode and len(self.text) < self.max_len:
                ch = event.unicode
                if self.numeric_dot and ch not in "0123456789.":
                    return
                if ch.isprintable():
                    self.text += ch

    def draw(self, surf: pygame.Surface) -> None:
        pygame.draw.rect(surf, (255, 255, 255), self.rect, border_radius=8)
        border = theme.GOLD if self.focused else theme.PANEL_LINE
        pygame.draw.rect(surf, border, self.rect, width=2, border_radius=8)
        font = theme.get_font(self.font_size)
        if self.text:
            txt = font.render(self.text, True, theme.TEXT)
        else:
            txt = font.render(self.placeholder, True, theme.TEXT_DIM)
        surf.blit(txt, (self.rect.x + 12, self.rect.centery - txt.get_height() // 2))
        # 光标
        if self.focused and (pygame.time.get_ticks() // 500) % 2 == 0:
            w = font.size(self.text)[0]
            cx = self.rect.x + 12 + w + 2
            pygame.draw.line(surf, theme.TEXT, (cx, self.rect.y + 8),
                             (cx, self.rect.bottom - 8), 2)


class Segmented:
    """一行单选按钮组（如：9 路 / 13 路 / 19 路）。"""

    def __init__(self, x: int, y: int, label: str, options, selected: int = 0,
                 on_change: Optional[Callable] = None, seg_w: int = 96, h: int = 40,
                 label_w: int = 96, font_size: int = 19):
        self.label = label
        self.options = list(options)
        self.selected = selected
        self.on_change = on_change
        self.label_pos = (x, y + h // 2)
        self.font_size = font_size
        self.rects = [pygame.Rect(x + label_w + i * (seg_w + 8), y, seg_w, h)
                      for i in range(len(self.options))]
        self.visible = True

    def handle(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(event.pos):
                    self.selected = i
                    if self.on_change:
                        self.on_change(i)
                    return True
        return False

    def draw(self, surf: pygame.Surface) -> None:
        if not self.visible:
            return
        f = theme.get_font(self.font_size, bold=True)
        t = f.render(self.label, True, theme.TEXT)
        surf.blit(t, (self.label_pos[0], self.label_pos[1] - t.get_height() // 2))
        for i, (r, opt) in enumerate(zip(self.rects, self.options)):
            on = i == self.selected
            pygame.draw.rect(surf, theme.BTN if on else (255, 255, 255), r, border_radius=10)
            pygame.draw.rect(surf, theme.GOLD if on else theme.PANEL_LINE, r, width=2, border_radius=10)
            tt = f.render(opt, True, theme.BTN_TEXT if on else theme.TEXT)
            surf.blit(tt, tt.get_rect(center=r.center))
