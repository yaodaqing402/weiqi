"""界面主题：配色、尺寸、字体加载。"""
from __future__ import annotations

import pygame

# ---------- 窗口 / 布局 ----------
WIDTH = 1040
HEIGHT = 720
FPS = 60

BOARD_SIDE = HEIGHT               # 左侧正方形棋盘区域 720x720
PANEL_X = BOARD_SIDE              # 右侧信息面板起点

# ---------- 配色 ----------
BG = (238, 224, 200)             # 整体背景（米黄）
BOARD_BG = (226, 184, 112)       # 棋盘木色（榧木）
BOARD_BG2 = (212, 168, 98)       # 棋盘木色（深）
LINE = (70, 48, 24)              # 棋盘线条
COORD_TEXT = (110, 80, 45)
PANEL_BG = (248, 241, 228)
PANEL_LINE = (210, 195, 168)

BLACK_STONE = (28, 28, 32)
BLACK_STONE_HI = (78, 78, 86)    # 黑子高光
WHITE_STONE = (246, 245, 240)
WHITE_STONE_EDGE = (168, 164, 154)
WHITE_STONE_SHADE = (226, 224, 216)
STONE_SHADOW = (170, 132, 80)    # 棋子投影（偏暗木色，不透明，跨后端稳定）

RED = (196, 48, 43)              # 标题 / 强调
SELECT = (60, 160, 90)           # 提示点
LAST_MOVE = (220, 60, 50)        # 最后一手标记
ATARI = (230, 120, 30)           # 被叫吃提醒
TARGET = (220, 60, 50)           # 练习题目标
CHECK = (220, 60, 50)            # 提醒文字

TEXT = (60, 45, 30)
TEXT_DIM = (130, 115, 95)
TEXT_LIGHT = (250, 245, 235)

BTN = (176, 92, 60)
BTN_HOVER = (196, 112, 74)
BTN_DISABLED = (188, 176, 158)
BTN_TEXT = (252, 246, 236)
GOLD = (208, 158, 60)

_font_cache: dict = {}
# 跨平台中文字体候选（按优先级）
_CJK_CANDIDATES = [
    "PingFang SC", "STHeiti", "Heiti SC", "Hiragino Sans GB",
    "Microsoft YaHei", "微软雅黑", "SimHei", "黑体",
    "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS",
    "WenQuanYi Micro Hei",
]
_cjk_font_name = None


def _resolve_cjk() -> str:
    global _cjk_font_name
    if _cjk_font_name is not None:
        return _cjk_font_name
    available = set(pygame.font.get_fonts())
    def norm(s: str) -> str:
        return s.lower().replace(" ", "")
    avail_norm = {norm(a): a for a in available}
    for cand in _CJK_CANDIDATES:
        key = norm(cand)
        if key in avail_norm:
            _cjk_font_name = pygame.font.match_font(avail_norm[key]) or cand
            return _cjk_font_name
        m = pygame.font.match_font(cand)
        if m:
            _cjk_font_name = m
            return _cjk_font_name
    # 兜底：让 pygame 自选，可能不含中文，但不至于崩溃
    _cjk_font_name = pygame.font.match_font("arial") or pygame.font.get_default_font()
    return _cjk_font_name


def draw_veil(surf: pygame.Surface, alpha: int = 140) -> None:
    """在整屏铺一层半透明黑色遮罩。用表面级 alpha（set_alpha），
    而非逐像素 alpha 表面——后者在部分显卡/Retina 后端上会被渲染成纯黑块。"""
    veil = pygame.Surface(surf.get_size())
    veil.fill((0, 0, 0))
    veil.set_alpha(alpha)
    surf.blit(veil, (0, 0))


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _font_cache:
        f = pygame.font.Font(_resolve_cjk(), size)
        f.set_bold(bold)
        _font_cache[key] = f
    return _font_cache[key]
