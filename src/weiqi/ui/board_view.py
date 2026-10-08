"""棋盘与棋子的绘制，以及像素坐标 <-> 棋盘坐标的换算。支持 9 / 13 / 19 路。

注意：全部用不透明颜色直接画在主表面上，不用带 alpha 通道的临时表面——
后者在部分显卡 / Retina 后端上会被渲染成黑块（象棋版踩过的坑）。
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Set, Tuple

import pygame

from . import theme
from ..engine.board import Board
from ..engine.stones import BLACK, COL_LETTERS, WHITE, Point, star_points


class BoardView:
    def __init__(self, size: int):
        self.size = size
        side = theme.BOARD_SIDE
        # 第一条线到窗口边的距离：要放得下边线上的棋子 + 坐标文字
        self.margin = {9: 70, 13: 58, 19: 50}.get(size, 56)
        self.cell = (side - 2 * self.margin) / (size - 1)
        self.top = (theme.HEIGHT - side) // 2
        self.radius = int(self.cell * 0.47)
        self._bg: Optional[pygame.Surface] = None

    # ---------- 坐标换算 ----------
    def point_pos(self, r: int, c: int) -> Tuple[int, int]:
        x = self.margin + c * self.cell
        y = self.top + self.margin + r * self.cell
        return int(round(x)), int(round(y))

    def pos_to_cell(self, mx: int, my: int) -> Optional[Tuple[int, int]]:
        if mx >= theme.BOARD_SIDE:
            return None
        c = round((mx - self.margin) / self.cell)
        r = round((my - self.top - self.margin) / self.cell)
        if not (0 <= r < self.size and 0 <= c < self.size):
            return None
        x, y = self.point_pos(r, c)
        if (mx - x) ** 2 + (my - y) ** 2 > (self.cell * 0.5) ** 2:
            return None
        return r, c

    # ---------- 背景（棋盘线）----------
    def _build_bg(self) -> pygame.Surface:
        surf = pygame.Surface((theme.BOARD_SIDE, theme.HEIGHT))
        surf.fill(theme.BG)
        pad = self.margin - 6
        x0, y0 = self.point_pos(0, 0)
        x1, y1 = self.point_pos(self.size - 1, self.size - 1)
        board_rect = pygame.Rect(x0 - pad, y0 - pad, x1 - x0 + pad * 2, y1 - y0 + pad * 2)
        # 木纹渐变
        for i in range(board_rect.height):
            t = i / max(1, board_rect.height)
            col = tuple(int(theme.BOARD_BG[k] * (1 - t) + theme.BOARD_BG2[k] * t) for k in range(3))
            pygame.draw.line(surf, col, (board_rect.x, board_rect.y + i),
                             (board_rect.right, board_rect.y + i))
        pygame.draw.rect(surf, theme.LINE, board_rect, width=2, border_radius=6)

        n = self.size
        for i in range(n):
            w = 2 if i in (0, n - 1) else 1
            pygame.draw.line(surf, theme.LINE, self.point_pos(i, 0), self.point_pos(i, n - 1), w)
            pygame.draw.line(surf, theme.LINE, self.point_pos(0, i), self.point_pos(n - 1, i), w)
        star_r = 4 if n == 19 else 5
        for (r, c) in star_points(n):
            pygame.draw.circle(surf, theme.LINE, self.point_pos(r, c), star_r)
        # 坐标：上下写列字母，左右写行号（左下角为 A1）
        f = theme.get_font(15 if n == 19 else 17, bold=True)
        off = min(self.radius + 14, pad - 8)   # 坐标写在木框内、边线棋子外侧
        for i in range(n):
            letter = f.render(COL_LETTERS[i], True, theme.COORD_TEXT)
            x, _ = self.point_pos(0, i)
            surf.blit(letter, letter.get_rect(center=(x, y0 - off)))
            surf.blit(letter, letter.get_rect(center=(x, y1 + off)))
            num = f.render(str(n - i), True, theme.COORD_TEXT)
            _, y = self.point_pos(i, 0)
            surf.blit(num, num.get_rect(center=(x0 - off, y)))
            surf.blit(num, num.get_rect(center=(x1 + off, y)))
        return surf

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface, board: Board,
             last_move: Optional[Point] = None,
             hover: Optional[Point] = None,
             hover_color: Optional[str] = None,
             dead: Optional[Set[Point]] = None,
             owner: Optional[Dict[Point, Optional[str]]] = None,
             hint: Optional[Point] = None,
             target: Optional[Point] = None,
             atari: Iterable[Point] = (),
             fresh: Optional[Tuple[Point, float]] = None,
             numbers: Optional[Dict[Point, int]] = None) -> None:
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))
        dead = dead or set()
        atari = set(atari)

        # 数子阶段：标出每个点的归属
        if owner:
            s = max(4, int(self.cell * 0.22))
            for p, who in owner.items():
                if who is None:
                    continue
                x, y = self.point_pos(*p)
                col = theme.BLACK_STONE if who == BLACK else theme.WHITE_STONE
                rect = pygame.Rect(x - s // 2, y - s // 2, s, s)
                pygame.draw.rect(surf, col, rect)
                if who == WHITE:
                    pygame.draw.rect(surf, theme.WHITE_STONE_EDGE, rect, 1)

        for r in range(board.size):
            for c in range(board.size):
                v = board.grid[r][c]
                if v is None:
                    continue
                x, y = self.point_pos(r, c)
                rad = self.radius
                if fresh and fresh[0] == (r, c):
                    rad = int(self.radius * (1.0 + 0.25 * (1 - fresh[1])))
                self._stone(surf, x, y, rad, v, dim=(r, c) in dead)
                if (r, c) in atari and (r, c) not in dead:
                    pygame.draw.circle(surf, theme.ATARI, (x, y), self.radius + 2, 3)
                if numbers and (r, c) in numbers:
                    self._number(surf, x, y, numbers[(r, c)], v)

        if target is not None and board.at(target) is not None:
            self._triangle(surf, *self.point_pos(*target), theme.TARGET)

        if last_move is not None and board.at(last_move) is not None and not numbers:
            x, y = self.point_pos(*last_move)
            pygame.draw.circle(surf, theme.LAST_MOVE, (x, y), max(4, int(self.radius * 0.28)))

        if hint is not None:
            x, y = self.point_pos(*hint)
            pygame.draw.circle(surf, theme.SELECT, (x, y), self.radius, 4)
            pygame.draw.circle(surf, theme.SELECT, (x, y), max(3, self.radius // 4))

        if hover is not None and hover_color and board.at(hover) is None:
            # 鼠标悬停：画一个空心“影子棋子”，提示将要落子的位置
            x, y = self.point_pos(*hover)
            col = theme.BLACK_STONE if hover_color == BLACK else theme.WHITE_STONE_EDGE
            pygame.draw.circle(surf, col, (x, y), self.radius - 1, 2)
            pygame.draw.circle(surf, col, (x, y), max(2, self.radius // 5))

    def _stone(self, surf, x, y, radius, color, dim=False):
        pygame.draw.circle(surf, theme.STONE_SHADOW, (x + 2, y + 3), radius)
        if color == BLACK:
            pygame.draw.circle(surf, theme.BLACK_STONE, (x, y), radius)
            hi = max(2, radius // 3)
            pygame.draw.circle(surf, theme.BLACK_STONE_HI, (x - radius // 3, y - radius // 3), hi)
        else:
            # 右下方淡灰月牙阴影，显出立体感
            pygame.draw.circle(surf, theme.WHITE_STONE_SHADE, (x, y), radius)
            k = max(1, radius // 9)
            pygame.draw.circle(surf, theme.WHITE_STONE, (x - k, y - k), int(radius * 0.86))
            pygame.draw.circle(surf, theme.WHITE_STONE_EDGE, (x, y), radius, 1)
        if dim:
            # 死子：画叉
            k = int(radius * 0.5)
            col = theme.WHITE_STONE if color == BLACK else theme.BLACK_STONE
            pygame.draw.line(surf, col, (x - k, y - k), (x + k, y + k), 3)
            pygame.draw.line(surf, col, (x - k, y + k), (x + k, y - k), 3)

    def _number(self, surf, x, y, n, color):
        f = theme.get_font(max(11, int(self.radius * (0.9 if n < 100 else 0.7))), bold=True)
        col = theme.WHITE_STONE if color == BLACK else theme.BLACK_STONE
        t = f.render(str(n), True, col)
        surf.blit(t, t.get_rect(center=(x, y)))

    def _triangle(self, surf, x, y, color):
        k = max(5, int(self.radius * 0.45))
        pts = [(x, y - k), (x - k, y + int(k * 0.7)), (x + k, y + int(k * 0.7))]
        pygame.draw.polygon(surf, color, pts)
