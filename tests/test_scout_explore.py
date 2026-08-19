"""探索予算（explore / exploit）のテスト。

収益実績への加点をやめた代わりの仕組みなので、「勝っている市場ばかり再発見する
ループ」を実際に防げているかを検証する。
"""
from __future__ import annotations

from src.scout.explore import allocate, split_by_novelty
from src.scout.models import Candidate


def _pairs(*specs) -> list[tuple[Candidate, int]]:
    return [(Candidate(title=t, keywords=k), 1) for t, k in specs]


def test_採用ニッチがなければ全件が新規開拓扱い():
    candidates = _pairs(("A", ["インボイス"]), ("B", ["AI議事録"]))

    exploit, explore = split_by_novelty(candidates, [])

    assert exploit == []
    assert len(explore) == 2


def test_採用ニッチと語が重なれば深掘り扱い():
    candidates = _pairs(("A", ["インボイス"]), ("B", ["AI議事録"]))

    exploit, explore = split_by_novelty(candidates, ["インボイス 会計ソフト"])

    assert [c[0].title for c in exploit] == ["A"]
    assert [c[0].title for c in explore] == ["B"]


def test_初期は枠を絞らず調査枠を使い切る():
    """採用実績0件の時点で枠を分けると初動が遅れる。"""
    candidates = _pairs(("A", ["X"]), ("B", ["Y"]), ("C", ["Z"]))

    assert len(allocate(candidates, [], total_slots=3)) == 3


def test_実績がある場合は新規開拓枠が確保される():
    candidates = _pairs(("既存1", ["インボイス"]), ("既存2", ["インボイス"]),
                        ("既存3", ["インボイス"]), ("新規", ["AI議事録"]))

    picked = allocate(candidates, ["インボイス"], total_slots=3, explore_ratio=0.34)

    assert "新規" in [c[0].title for c in picked]   # 深掘りだけで埋めない


def test_片側が足りなければもう一方で埋める():
    """枠を守るために調査数を減らさない。"""
    candidates = _pairs(("既存1", ["インボイス"]), ("既存2", ["インボイス"]),
                        ("既存3", ["インボイス"]))

    picked = allocate(candidates, ["インボイス"], total_slots=3, explore_ratio=0.5)

    assert len(picked) == 3


def test_枠がゼロなら何も選ばない():
    assert allocate(_pairs(("A", ["X"])), [], total_slots=0) == []


# --- 状態依存の explore 枠 ---------------------------------------------------
def test_勝ちパターンがなければ全枠が探索になる():
    """N=0 では exploit 対象そのものが存在しない。比率を固定しない。"""
    from src.scout.explore import explore_ratio_for

    assert explore_ratio_for(0) == 1.00


def test_勝ちが増えるほど探索枠は縮む():
    from src.scout.explore import explore_ratio_for

    ratios = [explore_ratio_for(w) for w in (0, 1, 3, 5)]

    assert ratios == sorted(ratios, reverse=True)
    assert ratios[-1] >= 0.15                # 深掘りだけにはしない


def test_勝ち数を渡すと比率が上書きされる():
    candidates = _pairs(("既存1", ["インボイス"]), ("既存2", ["インボイス"]),
                        ("新規", ["AI議事録"]))

    # winners=0 なら全枠 explore なので、深掘り候補は選ばれない
    picked = allocate(candidates, ["インボイス"], total_slots=1,
                      explore_ratio=0.2, winners=0)

    assert [c[0].title for c in picked] == ["新規"]
