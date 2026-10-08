"""引擎规则回归测试：提子、禁着、打劫、数子、读子、练习题、AI、KataGo GTP 通信。"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
# 测试数据写到临时目录，不污染用户数据
os.environ.setdefault("WEIQI_DATA_DIR", os.path.join(
    os.path.dirname(__file__), "..", ".pytest_cache", "weiqi_data"))

from weiqi.engine import tactics
from weiqi.engine.ai import AI, RULE_CAPTURE, RULE_TERRITORY
from weiqi.engine.board import Board, IllegalMove
from weiqi.engine.katago import KataGo, from_vertex, to_vertex
from weiqi.engine.stones import BLACK, WHITE
from weiqi.game.controller import GameController, PHASE_OVER, PHASE_SCORING
from weiqi.game.notation import coord
from weiqi.game.puzzles import clean_puzzles, defender_move, solution_move, PUZZLES


def build(rows):
    b = Board(len(rows))
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == "X":
                b.grid[r][c] = BLACK
            elif ch in "O@":
                b.grid[r][c] = WHITE
    return b


# ---------- 规则 ----------
def test_capture_single_stone():
    b = build([".....", "..X..", ".XO..", "..X..", "....."])
    b.turn = BLACK
    cap = b.play((2, 3))
    assert cap == [(2, 2)]
    assert b.at((2, 2)) is None
    assert b.captures[BLACK] == 1


def test_suicide_is_illegal():
    b = build([".X...", "X....", ".....", ".....", "....."])
    b.turn = WHITE
    assert not b.is_legal(0, 0, WHITE)
    with pytest.raises(IllegalMove):
        b.play((0, 0))


def test_capture_beats_suicide():
    # 白下 (0,0)：自身没有空邻点，但能提掉黑 (0,1)，所以合法
    b = build([".XO..", "XO...", ".....", ".....", "....."])
    b.turn = WHITE
    assert b.is_legal(0, 0, WHITE)
    assert b.play((0, 0)) == [(0, 1)]


def test_simple_ko():
    b = build([
        ".XO..",
        "X.XO.",
        ".XO..",
        ".....",
        ".....",
    ])
    b.turn = WHITE
    cap = b.play((1, 1))          # 白提黑 (1,2)
    assert cap == [(1, 2)]
    assert b.ko == (1, 2)
    assert not b.is_legal(1, 2, BLACK)     # 黑不能立即提回
    b.play((4, 4))                          # 黑找劫材
    b.play((4, 0))                          # 白应
    assert b.is_legal(1, 2, BLACK)          # 隔一手后可以提回


def test_pass_and_area_score():
    b = Board(5)
    # 黑占左两列+中线，白占右两列
    for r in range(5):
        b.grid[r][2] = BLACK
        b.grid[r][3] = WHITE
    black, white, owner = b.area_score()
    assert black == 15 and white == 10
    winner, margin, _, _ = b.score_result(komi=7.5)
    assert winner == WHITE and margin == 2.5
    # 死子：把白棋里的一颗黑子算死
    b.grid[2][4] = BLACK
    black2, white2, _ = b.area_score({(2, 4)})
    assert (black2, white2) == (15, 10)


def test_eye_detection():
    b = build([
        ".X...",
        "X.X..",
        ".X...",
        ".....",
        ".....",
    ])
    assert b.is_eye(1, 1, BLACK)
    assert not b.is_eye(1, 1, WHITE)


# ---------- 读子 ----------
def test_ladder_reading():
    rows = PUZZLES[2].rows
    b = build(rows)
    b.turn = BLACK
    t = (3, 3)
    assert tactics.capture_move(b, t) == (3, 2)
    # 方向错了：白子逃掉
    b2 = b.clone()
    b2.play((3, 4))
    assert not tactics.is_dead_lost(b2, t)


def test_net_needs_non_atari_move():
    p = PUZZLES[3]
    b = p.build_board()
    st, libs = b.group(*p.target)
    for lib in libs:
        bb = b.clone()
        bb.play(lib)
        assert not tactics.is_dead_lost(bb, p.target), f"直接叫吃 {lib} 不应成功"
    bb = b.clone()
    bb.play((3, 5))
    assert tactics.is_dead_lost(bb, p.target)


# ---------- 练习题 ----------
def _solve(p):
    """黑方按正解走，白方用练习题防守逻辑，返回是否在步数内过关。"""
    b = p.build_board()
    used = 0
    while used < p.max_moves:
        move = solution_move(p, b)
        assert move is not None, f"{p.name}: 找不到解"
        b.play(move)
        used += 1
        if p.solved(b):
            return True
        b.play(defender_move(p, b))
        if p.solved(b):
            return True
    return False


def test_puzzles_valid_and_solvable():
    ps = clean_puzzles()
    assert len(ps) == len(PUZZLES)
    for p in ps:
        assert _solve(p), p.name


def test_puzzle_wrong_direction_fails():
    p = PUZZLES[2]
    b = p.build_board()
    b.play((3, 4))                     # 错误方向叫吃
    b.play(defender_move(p, b))
    assert b.liberty_count(*p.target) >= 3


# ---------- 控制器 ----------
def test_controller_two_passes_enter_scoring():
    g = GameController("pvp", rule=RULE_TERRITORY, size=9)
    g.play((4, 4))
    g.play(None)
    g.play(None)
    assert g.phase == PHASE_SCORING
    g.confirm_score()
    assert g.phase == PHASE_OVER and g.winner == BLACK   # 81 子 vs 0 + 7.5
    assert g.undo_once() and g.phase != PHASE_OVER


def test_controller_capture_game_ends():
    g = GameController("pvp", rule=RULE_CAPTURE, size=9, capture_target=1)
    for m in [(4, 4), (3, 4), (0, 0), (4, 3), (0, 1), (5, 4), (0, 2), (4, 5)]:
        g.play(m)
    assert g.winner == WHITE and g.over


def test_controller_toggle_dead_group():
    g = GameController("pvp", rule=RULE_TERRITORY, size=9)
    g.play((0, 0))
    g.play((0, 1))
    g.play(None)
    g.play(None)
    assert g.toggle_dead((0, 1))
    assert (0, 1) in g.dead


def test_notation():
    assert coord(19, (0, 0)) == "A19"
    assert coord(19, (18, 8)) == "J1"     # 跳过 I
    assert coord(9, None) == "停一手"
    assert to_vertex(19, (15, 3)) == "D4"
    assert from_vertex(19, "D4") == (15, 3)
    assert from_vertex(9, "pass") is None
    assert from_vertex(9, "resign") == "resign"


# ---------- AI ----------
def test_ai_takes_capture_and_saves():
    b = build([".........", ".........", ".........", "....X....",
               "...X@X...", ".........", ".........", ".........", "........."])
    ai = AI(3, rule=RULE_CAPTURE, capture_target=1, rng=random.Random(0))
    assert ai.choose(b, BLACK) == (5, 4)
    # 白方被叫吃时应逃跑
    b.turn = WHITE
    assert ai.choose(b, WHITE) == (5, 4)


@pytest.mark.parametrize("rule", [RULE_CAPTURE, RULE_TERRITORY])
def test_full_ai_game_terminates(rule):
    g = GameController("pvp", rule=rule, size=9, capture_target=5)
    ais = {BLACK: AI(1, rule, 5, random.Random(1)), WHITE: AI(3, rule, 5, random.Random(2))}
    for _ in range(300):
        if g.phase != "play":
            break
        m = ais[g.turn].choose(g.board, g.turn)
        if m is not None:
            assert g.board.is_legal(m[0], m[1])
        g.play(m)
    assert g.phase != "play", "对局应在 300 手内结束"


# ---------- KataGo GTP（用假引擎测试通信流程）----------
FAKE_GTP = os.path.join(os.path.dirname(__file__), "fake_gtp.py")


def test_katago_gtp_roundtrip():
    eng = KataGo(cmd=[sys.executable, FAKE_GTP])
    eng.start()
    try:
        mv = eng.genmove(9, [(BLACK, (4, 4))], WHITE)
        assert isinstance(mv, tuple) and mv != (4, 4)
        assert eng.genmove(9, [], BLACK) == (0, 0)
        dead = eng.dead_stones(9, [(BLACK, (0, 0)), (WHITE, (8, 8))])
        assert dead == {(8, 8)}
    finally:
        eng.close()
    assert not eng.alive


def test_bundled_katago_is_preferred_when_present():
    from weiqi.engine import katago
    found = katago.find_all_katago({})
    bundled = katago.bundled_executables()
    if bundled:
        assert found[:len(bundled)] == bundled          # 自带的排在本机安装的前面
    assert katago.find_all_katago({"katago_path": __file__})[0] == __file__
