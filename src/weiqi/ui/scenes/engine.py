"""AI 引擎设置：检测 KataGo 程序与模型、测试引擎、给出安装指引。"""
from __future__ import annotations

import os
import threading

import pygame

from .. import theme
from ..app import Scene
from ..widgets import Button
from ...engine import katago

GREY = (150, 120, 90)

GUIDE = [
    "安装包已自带 KataGo 引擎和模型（含人类风格模型），不用另外安装，打开就能用。",
    "· 正式对局的电脑、提示、数子时判断死子都由 KataGo 完成；吃子棋由内置战术 AI 陪下。",
    "· Windows 自带显卡版（OpenCL）和 CPU 版：先用显卡版，显卡不可用时自动换 CPU 版。",
    "　首次使用显卡版会自动调优，可能要等一两分钟，之后就很快了。",
    "· 想换用自己安装的 KataGo 或其它模型：把文件放进下方「引擎文件夹」，",
    "　或在设置文件 settings.json 里填写 katago_path / katago_model / katago_human_model。",
]


class EngineScene(Scene):
    def on_enter(self) -> None:
        self.test_msg = ""
        self.test_ok = None
        self._testing = False
        self._refresh()
        cx = theme.WIDTH // 2
        y = theme.HEIGHT - 84
        self.buttons = [
            Button((cx - 460, y, 170, 52), "重新检测", self._refresh_click, font_size=21),
            Button((cx - 275, y, 200, 52), "打开引擎文件夹", self._open_folder, font_size=21),
            Button((cx - 60, y, 170, 52), "测试引擎", self._test, font_size=21),
            Button((cx + 125, y, 170, 52), "", self._toggle_use, font_size=21, color=GREY),
            Button((cx + 310, y, 150, 52), "返回菜单", self._to_menu, font_size=21, color=GREY),
        ]
        self._update_use_label()

    def _refresh(self) -> None:
        self.status = katago.engine_status(self.app.settings)

    def _refresh_click(self) -> None:
        self.app.sound.play("button")
        self._refresh()
        self.test_msg = ""

    def _open_folder(self) -> None:
        self.app.sound.play("button")
        katago.open_folder(katago.katago_folder())

    def _toggle_use(self) -> None:
        self.app.sound.play("button")
        s = self.app.settings
        s["use_katago"] = not s.get("use_katago", True)
        self.app.save()
        self._update_use_label()

    def _update_use_label(self) -> None:
        on = self.app.settings.get("use_katago", True)
        self.buttons[3].label = "已启用" if on else "已停用"
        self.buttons[3].color = theme.SELECT if on else GREY

    def _test(self) -> None:
        if self._testing:
            return
        self.app.sound.play("button")
        if not (self.status["katago"] and self.status["model"]):
            self.test_ok, self.test_msg = False, "还缺程序或主模型，先按下面的说明安装"
            return
        self._testing = True
        self.test_ok, self.test_msg = None, "正在启动 KataGo…（首次运行可能要一两分钟）"

        def work():
            eng = katago.KataGo(level=2, settings=self.app.settings)
            try:
                eng.start()
                mv = eng.genmove(9, [], "b")
                human = "人类风格模型已启用" if eng.uses_human else "未用人类风格模型"
                self.test_ok = True
                self.test_msg = f"引擎正常！版本 {eng.version or '?'}，{human}，试下一手：" \
                                f"{katago.to_vertex(9, mv) if mv != 'resign' else '认输'}"
            except katago.EngineError as e:
                self.test_ok, self.test_msg = False, f"失败：{e}"
            finally:
                eng.close()
                self._testing = False
        threading.Thread(target=work, daemon=True).start()

    def _to_menu(self) -> None:
        self.app.sound.play("button")
        from .menu import MenuScene
        self.app.go(MenuScene(self.app))

    def handle(self, event: pygame.event.Event) -> None:
        for b in self.buttons:
            b.handle(event)

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(theme.BG)
        title = theme.get_font(40, bold=True).render("AI 引擎（KataGo）", True, theme.RED)
        surf.blit(title, (60, 36))
        card = pygame.Rect(60, 100, theme.WIDTH - 120, 214)
        pygame.draw.rect(surf, theme.PANEL_BG, card, border_radius=14)
        pygame.draw.rect(surf, theme.PANEL_LINE, card, width=2, border_radius=14)
        rows = [
            ("KataGo 程序", self.status["katago"], True),
            ("主模型", self.status["model"], True),
            ("人类风格模型", self.status["human_model"], False),
        ]
        y = card.y + 20
        for label, path, required in rows:
            ok = bool(path)
            mark_col = theme.SELECT if ok else (theme.CHECK if required else theme.TEXT_DIM)
            pygame.draw.circle(surf, mark_col, (card.x + 30, y + 14), 9)
            surf.blit(theme.get_font(21, bold=True).render(label, True, theme.TEXT), (card.x + 50, y))
            text = self._short(path) if ok else ("未找到" if required else "未找到（可选）")
            if ok and katago.is_bundled(path):
                text = "安装包自带 · " + os.path.basename(path)
            surf.blit(theme.get_font(17).render(text, True, theme.TEXT if ok else theme.TEXT_DIM),
                      (card.x + 210, y + 3))
            y += 42
        f = theme.get_font(17)
        folder = f"引擎文件夹：{self._short(katago.katago_folder(), 80)}"
        surf.blit(f.render(folder, True, theme.TEXT_DIM), (card.x + 24, y))
        ready = self.status["katago"] and self.status["model"]
        use = self.app.settings.get("use_katago", True)
        summary = ("可以使用：正式对局将由 KataGo 陪你下" if ready and use else
                   "已停用：正式对局使用内置 AI" if ready else
                   "暂不可用：正式对局使用内置 AI（吃子棋始终用内置 AI）")
        surf.blit(theme.get_font(18, bold=True).render(summary, True,
                  theme.SELECT if ready and use else theme.ATARI), (card.x + 24, y + 28))
        y = card.bottom + 18
        for i, line in enumerate(GUIDE):
            font = theme.get_font(18, bold=(i == 0))
            surf.blit(font.render(line, True, theme.TEXT if i == 0 else theme.TEXT_DIM), (60, y))
            y += 30
        if self.test_msg:
            col = theme.SELECT if self.test_ok else (theme.CHECK if self.test_ok is False else theme.GOLD)
            t = theme.get_font(18, bold=True).render(self.test_msg[:70], True, col)
            surf.blit(t, (60, theme.HEIGHT - 124))
        for b in self.buttons:
            b.draw(surf)

    @staticmethod
    def _short(path: str, n: int = 64) -> str:
        path = path.replace(os.path.expanduser("~"), "~")
        return path if len(path) <= n else "…" + path[-(n - 1):]
