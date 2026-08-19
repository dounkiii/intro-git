"""投資レベル（commitment level）のテスト。

要件: confidence は「やる/やらない」ではなく「いくら賭けるか」を決める変数であること。
高Opportunity × 低Confidence を watch で放置せず、小さく試せること。
"""
from __future__ import annotations

from src.scout.commitment import (ADOPT, CHEAP_TEST, EXIT, OBSERVE, SCALE,
                                  budget_for, initial_level, next_level)


# --- 初期レベル -------------------------------------------------------------
def test_確信が低くても機会が高ければ小さく試す():
    """ここが本題。watch で放置すると他者に取られる。"""
    assert initial_level("watch", confidence=0.2, opportunity=60) == CHEAP_TEST
    assert initial_level("now", confidence=0.2, opportunity=70) == CHEAP_TEST


def test_確信が高ければ通常運用で始める():
    assert initial_level("now", confidence=0.8, opportunity=70) == ADOPT


def test_確信が高くてもnow判定でなければ小さく試す():
    assert initial_level("watch", confidence=0.8, opportunity=50) == CHEAP_TEST


def test_機会が低ければ何もしない():
    assert initial_level("watch", confidence=0.9, opportunity=5) == OBSERVE


def test_捨てる判定は何もしない():
    assert initial_level("drop", confidence=0.9, opportunity=80) == OBSERVE


# --- 予算 -------------------------------------------------------------------
def test_レベルが上がるほど生成枠が増える():
    budgets = [budget_for(lv).items_per_run for lv in (OBSERVE, CHEAP_TEST, ADOPT, SCALE)]

    assert budgets == sorted(budgets)
    assert budget_for(OBSERVE).items_per_run == 0
    assert budget_for(EXIT).items_per_run == 0


def test_小さく試すには公開上限がある():
    """上限が無いと「小さく試す」が成立しない。"""
    assert 0 < budget_for(CHEAP_TEST).test_posts <= 5
    assert budget_for(ADOPT).test_posts == 0          # 0 = 上限なし


# --- 遷移 -------------------------------------------------------------------
def test_売上が出たら枠を増やす():
    level, why = next_level(CHEAP_TEST, stage=5, decided=True, revenue_jpy=3200,
                            posts=3, creatives_tried=1)

    assert level == SCALE
    assert "売上" in why


def test_判定不能ではレベルを動かさない():
    """データが無いことを「悪い」と読み替えない。"""
    level, why = next_level(CHEAP_TEST, stage=0, decided=False, revenue_jpy=0,
                            posts=1, creatives_tried=1)

    assert level == CHEAP_TEST
    assert "不足" in why


def test_配信されなくても切り口を試していなければ撤退しない():
    level, why = next_level(CHEAP_TEST, stage=1, decided=True, revenue_jpy=0,
                            posts=3, creatives_tried=1)

    assert level == CHEAP_TEST
    assert "切り口" in why


def test_複数の切り口で配信されなければ撤退する():
    level, why = next_level(CHEAP_TEST, stage=1, decided=True, revenue_jpy=0,
                            posts=9, creatives_tried=3)

    assert level == EXIT


def test_配信が成立していれば通常運用に上がる():
    """Stage 2〜4 は配信は出来ている = ニッチの問題ではない。"""
    level, why = next_level(CHEAP_TEST, stage=3, decided=True, revenue_jpy=0,
                            posts=3, creatives_tried=1)

    assert level == ADOPT


def test_撤退済みと監視のみは動かさない():
    assert next_level(EXIT, 5, True, 9999, 10, 3)[0] == EXIT
    assert next_level(OBSERVE, 5, True, 9999, 10, 3)[0] == OBSERVE
