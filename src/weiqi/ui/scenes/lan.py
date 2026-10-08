"""局域网联机设置：创建房间（主机/执黑，决定玩法与棋盘）或加入房间（客户端/执白）。"""
from __future__ import annotations

import pygame

from .. import theme
from ..app import Scene
from ..widgets import Button, Segmented, TextInput
from ...engine.ai import RULE_CAPTURE, RULE_TERRITORY
from ...engine.stones import SIZES
from ...net.lan import NetGame, DEFAULT_PORT, local_ip

RULES = [RULE_CAPTURE, RULE_TERRITORY]
TARGETS = [1, 3, 5]
GREY = (150, 120, 90)


class LanScene(Scene):
    def on_enter(self) -> None:
        self.state = "choose"     # choose / host / join
        self.net = None
        self.error = ""
        self._ip = local_ip()
        self._build_choose()

    # ---------- 选择 ----------
    def _build_choose(self) -> None:
        s = self.app.settings
        cx = theme.WIDTH // 2
        x = cx - 250
        rule_idx = RULES.index(s.get("rule")) if s.get("rule") in RULES else 0
        size_idx = SIZES.index(s.get("board_size")) if s.get("board_size") in SIZES else 0
        tgt_idx = TARGETS.index(s.get("capture_target")) if s.get("capture_target") in TARGETS else 1
        self._rule = Segmented(x, 220, "玩法", ["吃子棋", "正式对局"], rule_idx,
                               self._on_rule, seg_w=150)
        self._size = Segmented(x, 272, "棋盘", ["9 路", "13 路", "19 路"], size_idx, seg_w=110)
        self._target = Segmented(x, 324, "吃几子", ["先吃 1 子", "先吃 3 子", "先吃 5 子"],
                                 tgt_idx, seg_w=110)
        self._on_rule(rule_idx)
        self.widgets = [
            self._rule, self._size, self._target,
            Button((cx - 330, 400, 320, 64), "创建房间（执黑先行）", self._host, font_size=24),
            Button((cx + 10, 400, 320, 64), "加入房间（执白后行）",
                   self._join_form, font_size=24, color=theme.BLACK_STONE),
            Button((cx - 160, 500, 320, 54), "返回菜单", self._to_menu,
                   font_size=22, color=GREY),
        ]
        self.ip_input = None

    def _on_rule(self, i: int) -> None:
        self._target.visible = RULES[i] == RULE_CAPTURE

    def _host(self) -> None:
        self.app.sound.play("button")
        self._setup = {
            "rule": RULES[self._rule.selected],
            "size": SIZES[self._size.selected],
            "capture_target": TARGETS[self._target.selected],
        }
        self.state = "host"
        self.net = NetGame("host")
        self.net.host(DEFAULT_PORT)
        cx = theme.WIDTH // 2
        self.widgets = [
            Button((cx - 120, 500, 240, 54), "取消", self._cancel, font_size=22, color=GREY),
        ]

    def _join_form(self) -> None:
        self.app.sound.play("button")
        self.state = "join"
        cx = theme.WIDTH // 2
        self.ip_input = TextInput((cx - 160, 300, 320, 52), placeholder="输入主机 IP，如 192.168.1.5",
                                  max_len=15, font_size=22, numeric_dot=True)
        self.ip_input.focused = True
        self.widgets = [
            self.ip_input,
            Button((cx - 160, 380, 150, 52), "连接", self._connect, font_size=22),
            Button((cx + 10, 380, 150, 52), "返回", self._cancel, font_size=22, color=GREY),
        ]

    def _connect(self) -> None:
        ip = (self.ip_input.text or "").strip()
        if not ip:
            self.error = "请输入主机 IP 地址"
            return
        self.app.sound.play("button")
        self.error = ""
        if self.net:
            self.net.close()
        self.net = NetGame("client")
        self.net.join(ip, DEFAULT_PORT)

    def _cancel(self) -> None:
        if self.net:
            self.net.close()
            self.net = None
        self.error = ""
        self.on_enter()

    def _to_menu(self) -> None:
        self.app.sound.play("button")
        from .menu import MenuScene
        self.app.go(MenuScene(self.app))

    # ---------- 事件 / 更新 ----------
    def handle(self, event: pygame.event.Event) -> None:
        for w in list(self.widgets):
            w.handle(event)

    def update(self, dt: float) -> None:
        if self.net and self.net.status == "connected":
            from .game import GameScene
            if self.net.role == "host":
                st = self._setup
                self.net.send_setup(st["rule"], st["size"], st["capture_target"])
                self.app.go(GameScene(self.app, mode="lan", net=self.net, **st))
                return
            # 客户端：等主机发来对局设置
            for msg in self.net.poll():
                if msg.get("type") == "setup":
                    self.app.go(GameScene(self.app, mode="lan", net=self.net,
                                          rule=msg.get("rule", RULE_CAPTURE),
                                          size=int(msg.get("size", 9)),
                                          capture_target=int(msg.get("capture_target", 3))))
                    return
        elif self.net and self.net.status in ("error", "closed"):
            self.error = f"连接失败：{self.net.error or '请检查 IP 与网络'}"
            self.net = None
            if self.state == "host":
                self._build_choose()
                self.state = "choose"

    # ---------- 绘制 ----------
    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(theme.BG)
        title = theme.get_font(40, bold=True).render("局域网联机", True, theme.RED)
        surf.blit(title, title.get_rect(centerx=theme.WIDTH // 2, y=80))
        if self.state == "choose":
            tip = "两台电脑连到同一个 Wi-Fi / 局域网，一台创建、一台加入即可对弈"
            self._center_text(surf, tip, 150, theme.get_font(20), theme.TEXT_DIM)
            self._center_text(surf, "（玩法和棋盘由创建房间的一方决定）", 180,
                              theme.get_font(17), theme.TEXT_DIM)
        elif self.state == "host":
            self._center_text(surf, "房间已创建，等待对方加入…", 200,
                              theme.get_font(26, bold=True), theme.TEXT)
            self._center_text(surf, f"本机 IP：{self._ip}", 270,
                              theme.get_font(30, bold=True), theme.GOLD)
            self._center_text(surf, f"端口：{DEFAULT_PORT}", 320,
                              theme.get_font(22), theme.TEXT_DIM)
            st = self._setup
            rule = f"吃子棋 · 先吃 {st['capture_target']} 子" if st["rule"] == RULE_CAPTURE else "正式对局"
            self._center_text(surf, f"{rule} · {st['size']} 路", 370,
                              theme.get_font(22, bold=True), theme.TEXT)
            self._center_text(surf, "把上面的 IP 告诉对方，让对方选择“加入房间”并输入", 420,
                              theme.get_font(18), theme.TEXT_DIM)
        elif self.state == "join":
            self._center_text(surf, "输入主机的 IP 地址后点击连接", 250,
                              theme.get_font(22), theme.TEXT)
            if self.net and self.net.status == "connecting":
                self._center_text(surf, "正在连接…", 450, theme.get_font(22), theme.GOLD)
            elif self.net and self.net.status == "connected":
                self._center_text(surf, "已连接，等待主机开局…", 450, theme.get_font(22), theme.GOLD)
        if self.error:
            self._center_text(surf, self.error, 590, theme.get_font(20, bold=True), theme.CHECK)
        for w in self.widgets:
            w.draw(surf)

    def _center_text(self, surf, text, y, font, color) -> None:
        t = font.render(text, True, color)
        surf.blit(t, t.get_rect(centerx=theme.WIDTH // 2, y=y))
