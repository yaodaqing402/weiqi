"""玩家段位与积分成长系统——引导小朋友逐步提升。"""
from __future__ import annotations

from typing import Dict, Tuple

# (晋级所需积分下限, 段位名称)
RANKS = [
    (0, "小棋童"),
    (100, "围棋小苗 · 25级"),
    (250, "入门棋士 · 20级"),
    (450, "初级棋士 · 15级"),
    (700, "中级棋士 · 10级"),
    (1000, "高级棋士 · 5级"),
    (1400, "业余初段"),
    (1900, "围棋小国手"),
]


def rank_of(score: int) -> Tuple[int, str]:
    """返回 (段位序号, 段位名称)。"""
    idx = 0
    for i, (need, _name) in enumerate(RANKS):
        if score >= need:
            idx = i
    return idx, RANKS[idx][1]


def next_rank(score: int):
    """返回 (下一段位名称, 还差多少积分)；已满级返回 (None, 0)。"""
    idx, _ = rank_of(score)
    if idx + 1 >= len(RANKS):
        return None, 0
    need, name = RANKS[idx + 1]
    return name, need - score


def progress(score: int) -> float:
    """当前段位内的进度 0~1，用于进度条。"""
    idx, _ = rank_of(score)
    cur = RANKS[idx][0]
    if idx + 1 >= len(RANKS):
        return 1.0
    nxt = RANKS[idx + 1][0]
    return max(0.0, min(1.0, (score - cur) / (nxt - cur)))


def award(settings: Dict, won: bool, difficulty: int, draw: bool = False) -> Dict:
    """根据对局结果更新积分与胜负场次，返回变化说明。

    赢棋按难度加分（难度越高加分越多）；输棋小幅扣分但不低于 0，保护小朋友积极性。
    """
    before = settings.get("rank_score", 0)
    before_idx, before_name = rank_of(before)
    if draw:
        delta = 5
        settings["draws"] = settings.get("draws", 0) + 1
    elif won:
        delta = 20 + max(0, difficulty) * 15
        settings["wins"] = settings.get("wins", 0) + 1
    else:
        delta = -5
        settings["losses"] = settings.get("losses", 0) + 1
    score = max(0, before + delta)
    settings["rank_score"] = score
    after_idx, after_name = rank_of(score)
    return {
        "delta": score - before,
        "score": score,
        "promoted": after_idx > before_idx,
        "rank_name": after_name,
    }
