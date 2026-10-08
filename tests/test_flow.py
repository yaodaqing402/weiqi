"""界面流程测试（无显示环境）：人机整局、假 KataGo 接入、局域网联机、练习题过关、棋谱回放。"""
import os
import stat
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
_DATA = tempfile.mkdtemp(prefix="weiqi_test_")
os.environ["WEIQI_DATA_DIR"] = _DATA

from weiqi.engine.ai import AI                       # noqa: E402
from weiqi.engine.stones import BLACK, WHITE         # noqa: E402
from weiqi.game.record import list_records           # noqa: E402

FAKE_GTP = os.path.join(os.path.dirname(__file__), "fake_gtp.py")


@pytest.fixture(scope="module")
def app():
    from weiqi.ui.app import App
    a = App()
    yield a
    import pygame
    pygame.quit()


def pump(scene, secs=1.0, until=None):
    """推进若干帧（每帧 1/60 秒），直到 until() 为真。"""
    end = time.time() + secs
    while time.time() < end:
        scene.update(1 / 60)
        scene.draw(scene.app.screen)
        if until and until():
            return True
        time.sleep(0.002)
    return bool(until and until())


def click_point(scene, p):
    import pygame
    x, y = scene.view.point_pos(*p)
    scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))


def test_pve_capture_game_to_the_end(app):
    from weiqi.ui.scenes.game import GameScene
    app.settings["rank_score"] = 0
    g = GameScene(app, mode="pve", rule="capture", size=9, capture_target=1, difficulty=0)
    app.go(g)
    helper = AI(4, rule="capture", capture_target=1)
    for _ in range(120):
        if g.end_dialog:
            break
        if g.ctrl.turn == BLACK and g._idle():
            mv = helper.choose(g.ctrl.board, BLACK)
            if mv is None:
                g._pass()
            else:
                click_point(g, mv)
        pump(g, 2.0, until=lambda: g.end_dialog or (g.ctrl.turn == BLACK and g._idle()))
    assert g.end_dialog, "人机吃子棋应能下完"
    assert any(r.mode == "pve" for _p, r in list_records())
    assert app.settings["wins"] + app.settings["losses"] + app.settings.get("draws", 0) >= 1


def test_illegal_click_shows_message(app):
    from weiqi.ui.scenes.game import GameScene
    g = GameScene(app, mode="pvp", rule="territory", size=9)
    app.go(g)
    click_point(g, (4, 4))
    pump(g, 0.3)
    click_point(g, (4, 4))          # 已有棋子：不落子
    assert len(g.ctrl.moves) == 1


def _install_fake_katago():
    d = os.path.join(_DATA, "katago")
    os.makedirs(d, exist_ok=True)
    exe = os.path.join(d, "katago.exe" if os.name == "nt" else "katago")
    if os.name == "nt":
        pytest.skip("假引擎脚本仅在类 Unix 系统上测试")
    with open(exe, "w") as f:
        f.write(f"#!/bin/sh\nexec \"{sys.executable}\" \"{FAKE_GTP}\"\n")
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
    open(os.path.join(d, "kata1-fake-b18.bin.gz"), "wb").close()
    open(os.path.join(d, "b18c384nbt-humanv0.bin.gz"), "wb").close()
    return exe


def test_pve_territory_uses_katago(app):
    from weiqi.engine import katago
    from weiqi.ui.scenes.game import GameScene
    exe = _install_fake_katago()
    app.settings["katago_path"] = exe          # 指定路径优先于随包附带的引擎
    st = katago.engine_status(app.settings)
    assert st["katago"] == exe and st["model"] and st["human_model"]
    assert katago.find_all_katago(app.settings)[0] == exe
    g = GameScene(app, mode="pve", rule="territory", size=9, difficulty=2)
    app.go(g)
    assert pump(g, 10, until=lambda: g.engine_state == "ready"), g.engine_note
    assert g.engine.uses_human
    click_point(g, (4, 4))
    assert pump(g, 5, until=lambda: len(g.ctrl.moves) == 2)
    assert g.ctrl.moves[1] == (WHITE, (0, 0))      # 假引擎总下第一个空点 A9
    pump(g, 1, until=g._idle)
    # 提示走引擎
    g._hint()
    assert pump(g, 5, until=lambda: g.hint_point is not None)
    # 双方停一手 -> 数子 -> 引擎判死子（假引擎认为白子全死）
    g.ctrl.play(None)
    g.ctrl.play(None)
    assert pump(g, 5, until=lambda: g._dead_estimated and not g.busy.get("dead"))
    assert (0, 0) in g.ctrl.dead
    g._confirm_score()
    assert g.ctrl.over and g.ctrl.winner == BLACK
    app.go(g.__class__(app, mode="pvp"))           # 离开场景时关闭引擎
    time.sleep(0.5)
    assert not katago._live
    app.settings["katago_path"] = ""


def test_lan_game_over_localhost(app):
    from weiqi.net.lan import NetGame
    from weiqi.ui.scenes.game import GameScene
    port = 5931
    host, client = NetGame("host"), NetGame("client")
    host.host(port)
    time.sleep(0.3)
    client.join("127.0.0.1", port)
    for _ in range(100):
        if host.status == client.status == "connected":
            break
        time.sleep(0.05)
    assert host.status == client.status == "connected"
    gh = GameScene(app, mode="lan", net=host, rule="territory", size=9, use_engine=False)
    gc = GameScene(app, mode="lan", net=client, rule="territory", size=9, use_engine=False)
    gh.on_enter()
    gc.on_enter()
    click_point(gh, (2, 2))                        # 主机执黑落子
    pump(gh, 0.3)
    assert pump(gc, 2, until=lambda: len(gc.ctrl.moves) == 1)
    assert gc.ctrl.board.at((2, 2)) == BLACK
    pump(gc, 1, until=gc._idle)
    click_point(gc, (6, 6))                        # 客户端执白
    pump(gc, 0.3)
    assert pump(gh, 2, until=lambda: len(gh.ctrl.moves) == 2)
    pump(gh, 1, until=gh._idle)
    gh._pass()
    pump(gh, 0.3)
    assert pump(gc, 2, until=lambda: len(gc.ctrl.moves) == 3)
    pump(gc, 1, until=gc._idle)
    gc._pass()
    pump(gc, 0.3)
    assert pump(gh, 2, until=lambda: gh.ctrl.phase == "scoring")
    assert gc.ctrl.phase == "scoring"
    pump(gh, 2, until=lambda: gh._dead_estimated and not gh.busy.get("dead"))
    click_point(gh, (6, 6))                        # 主机把白子标死，同步到客户端
    assert pump(gc, 2, until=lambda: (6, 6) in gc.ctrl.dead)
    gh._confirm_score()
    assert pump(gc, 2, until=lambda: gc.ctrl.over)
    assert gc.ctrl.winner == gh.ctrl.winner == BLACK
    host.close()
    client.close()


def test_puzzle_pass_and_replay(app):
    from weiqi.game.puzzles import solution_move
    from weiqi.ui.scenes.game import GameScene
    from weiqi.ui.scenes.replay import ReplayScene
    g = GameScene(app, mode="puzzle", puzzle_index=4)     # 倒扑
    app.go(g)
    for _ in range(4):
        if g.end_dialog:
            break
        pump(g, 2, until=lambda: g.ctrl.turn == BLACK and g._idle())
        click_point(g, solution_move(g.puzzle, g.ctrl.board))
        pump(g, 2, until=lambda: g.end_dialog or (g.ctrl.turn == BLACK and g._idle()))
    assert g.end_dialog and g.ctrl.winner == BLACK
    assert g.puzzle.name in app.settings.get("puzzles_done", [])
    path = [p for p, r in list_records() if r.mode == "puzzle"][0]
    r = ReplayScene(app, path)
    app.go(r)
    r._goto(len(r.moves))
    assert r.board.at(g.puzzle.target) is None     # 回放到最后，目标白子已被提掉
