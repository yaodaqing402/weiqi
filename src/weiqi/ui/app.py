"""应用入口：窗口、主循环、场景管理、全局资源（音效/设置）。"""
from __future__ import annotations

import os
from typing import Optional

import pygame

from . import theme
from .sound import SoundManager
from ..game.storage import load_settings, save_settings


class Scene:
    """场景基类。子类实现事件处理、更新与绘制。"""
    def __init__(self, app: "App"):
        self.app = app

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        """离开场景时调用（关闭引擎进程等）。"""
        pass

    def handle(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surf: pygame.Surface) -> None:
        pass


class App:
    def __init__(self):
        # 让缩放采用线性过滤，全屏/放大时更平滑清晰
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")
        pygame.init()
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
        except pygame.error:
            pass
        self.settings = load_settings()
        # SCALED：按逻辑分辨率渲染后等比例缩放到窗口/全屏（含高分屏 Retina 全量后备缓冲），
        # 不拉伸变形，自动加黑边；RESIZABLE：允许自由缩放窗口。鼠标坐标由 pygame 自动换算。
        self._flags = pygame.SCALED | pygame.RESIZABLE
        self.fullscreen = False
        try:
            self.screen = pygame.display.set_mode((theme.WIDTH, theme.HEIGHT), self._flags, vsync=1)
        except pygame.error:
            # 无显示环境（如 CI 的 dummy 驱动）退化为普通窗口
            self.screen = pygame.display.set_mode((theme.WIDTH, theme.HEIGHT))
        pygame.display.set_caption("围棋 · 少儿版")
        self.clock = pygame.time.Clock()
        self.sound = SoundManager(enabled=self.settings.get("sound", True))
        self.running = True
        self.scene: Optional[Scene] = None

    def go(self, scene: Scene) -> None:
        if self.scene is not None and self.scene is not scene:
            self.scene.on_exit()
        self.scene = scene
        scene.on_enter()

    @staticmethod
    def _is_fullscreen_key(event: pygame.event.Event) -> bool:
        if event.key == pygame.K_F11:
            return True
        # Cmd+F（macOS）/ Ctrl+F：切换全屏，且不与文本输入冲突
        if event.key == pygame.K_f and (event.mod & (pygame.KMOD_META | pygame.KMOD_CTRL)):
            return True
        return False

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        pygame.display.toggle_fullscreen()

    def save(self) -> None:
        save_settings(self.settings)

    def run(self) -> None:
        # 延迟导入，避免循环引用
        from .scenes.menu import MenuScene
        self.go(MenuScene(self))
        while self.running:
            dt = self.clock.tick(theme.FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and self._is_fullscreen_key(event):
                    self.toggle_fullscreen()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE \
                        and self.fullscreen:
                    self.toggle_fullscreen()
                elif self.scene is not None:
                    self.scene.handle(event)
            if self.scene is not None:
                self.scene.update(dt)
                self.scene.draw(self.screen)
            pygame.display.flip()
        if self.scene is not None:
            self.scene.on_exit()
        self.save()
        pygame.quit()


def _selftest() -> int:
    """无显示环境自检（供 CI）：初始化窗口、构建各场景并各绘制一帧。"""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    app = App()
    from .scenes.menu import MenuScene
    from .scenes.game import GameScene
    from .scenes.records import RecordsScene
    app.go(MenuScene(app))
    app.scene.draw(app.screen)
    from .scenes.engine import EngineScene
    from .scenes.lan import LanScene
    for mode, rule, size in (("pvp", "territory", 19), ("pve", "capture", 9),
                             ("pve", "territory", 13), ("puzzle", "capture", 9)):
        app.go(GameScene(app, mode=mode, rule=rule, size=size, difficulty=1,
                         use_engine=False))
        app.scene.update(0.016)
        app.scene.draw(app.screen)
    for scene in (RecordsScene(app), EngineScene(app), LanScene(app)):
        app.go(scene)
        app.scene.draw(app.screen)
    # 检查随包附带的 KataGo：能找到；设置 WEIQI_SELFTEST_ENGINE=1 时还会真的启动并下一手
    from ..engine import katago
    st = katago.engine_status(app.settings)
    lines = [f"katago={st['katago']}", f"model={st['model']}", f"human={st['human_model']}"]
    if os.environ.get("WEIQI_SELFTEST_ENGINE"):
        eng = katago.KataGo(level=0, settings=app.settings)
        try:
            eng.start()
            lines.append(f"engine={eng.version} human={eng.uses_human} "
                         f"move={katago.to_vertex(9, eng.genmove(9, [], 'b'))}")
        finally:
            eng.close()
    print("\n".join(lines))
    out = os.environ.get("WEIQI_SELFTEST_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\nSELFTEST PASS\n")
    print("SELFTEST PASS")
    pygame.quit()
    return 0


def main() -> int:
    if os.environ.get("WEIQI_SELFTEST"):
        return _selftest()
    App().run()
    return 0
