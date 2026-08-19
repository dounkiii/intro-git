"""投資レベル（commitment level）のテスト。

要件: confidence は「やる/やらない」ではなく「いくら賭けるか」を決める変数であること。
高Opportunity × 低Confidence を watch で放置せず、小さく試せること。
"""
from __future__ import annotations

from src.scout.commitment import (ADOPT, CHEAP_TEST, EXIT, OBSERVE, SCALE,
                                  budget_for, initial_level, is_reproducible,
                                  next_level)


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


# --- 再現性ゲート -----------------------------------------------------------
def test_初回売上ではSCALEにしない():
    """1件の売上は偶然の可能性がある。初回の成功シグナルに過剰反応しない。"""
    level, why, diagnosing = next_level(
        CHEAP_TEST, stage=5, decided=True, revenue_jpy=3200, posts=3,
        creatives_tried=1, conversions=1, revenue_events=1)

    assert level == ADOPT              # 昇格はするが SCALE ではない
    assert "再現性が未確認" in why
    assert diagnosing == ""


def test_CVが2件以上なら再現性ありとしてSCALEする():
    level, why, _ = next_level(CHEAP_TEST, stage=5, decided=True, revenue_jpy=6400,
                               posts=8, creatives_tried=1, conversions=2,
                               revenue_events=1)

    assert level == SCALE
    assert "再現性を確認" in why


def test_売上を2回観測すれば再現性ありとする():
    """CV が取れないプラットフォームでも再現性を判定できるようにする。"""
    level, why, _ = next_level(CHEAP_TEST, stage=5, decided=True, revenue_jpy=6400,
                               posts=8, creatives_tried=1, conversions=None,
                               revenue_events=2)

    assert level == SCALE


def test_ADOPTのまま初回売上を繰り返してもSCALEには上がらない():
    level, _, _ = next_level(ADOPT, stage=5, decided=True, revenue_jpy=3200,
                             posts=8, creatives_tried=1, conversions=1,
                             revenue_events=1)

    assert level == ADOPT


def test_再現性の判定条件():
    assert is_reproducible(2, 1)[0] is True
    assert is_reproducible(None, 2)[0] is True
    assert is_reproducible(1, 1)[0] is False
    assert is_reproducible(None, 1)[0] is False


# --- 診断中フラグ -----------------------------------------------------------
def test_配信は成立していても診断中は昇格させない():
    """悪い導線に対して制作量だけ増やさないための歯止め。"""
    for stage, cause in ((2, "creative"), (3, "funnel"), (4, "offer")):
        level, why, diagnosing = next_level(
            CHEAP_TEST, stage=stage, decided=True, revenue_jpy=0, posts=8,
            creatives_tried=1, likely_cause=cause)

        assert level == CHEAP_TEST          # ADOPT に上げない
        assert diagnosing == cause
        assert "生成枠を増やさない" in why


def test_診断中は生成枠が抑えられる():
    for level in (ADOPT, SCALE):
        normal = budget_for(level).items_per_run
        diagnosing = budget_for(level, "offer").items_per_run

        assert diagnosing < normal
        assert diagnosing == 1


def test_売上が出れば診断中フラグは解除される():
    _, _, diagnosing = next_level(ADOPT, stage=5, decided=True, revenue_jpy=3200,
                                  posts=8, creatives_tried=1, conversions=1,
                                  revenue_events=1)

    assert diagnosing == ""


# --- その他の遷移 -----------------------------------------------------------
def test_判定不能ではレベルを動かさない():
    """データが無いことを「悪い」と読み替えない。"""
    level, why, _ = next_level(CHEAP_TEST, stage=0, decided=False, revenue_jpy=0,
                               posts=1, creatives_tried=1)

    assert level == CHEAP_TEST
    assert "不足" in why


def test_配信されなくても切り口を試していなければ撤退しない():
    level, why, _ = next_level(CHEAP_TEST, stage=1, decided=True, revenue_jpy=0,
                               posts=3, creatives_tried=1)

    assert level == CHEAP_TEST
    assert "切り口" in why


def test_複数の切り口で配信されなければ撤退する():
    level, _, _ = next_level(CHEAP_TEST, stage=1, decided=True, revenue_jpy=0,
                             posts=9, creatives_tried=3)

    assert level == EXIT


def test_撤退済みと監視のみは動かさない():
    assert next_level(EXIT, 5, True, 9999, 10, 3)[0] == EXIT
    assert next_level(OBSERVE, 5, True, 9999, 10, 3)[0] == OBSERVE


def test_明示的な採用は何もしないレベルに落とさない(tmp_path, monkeypatch):
    """`/adopt` を叩いたのに OBSERVE になると、人間の指示が無視される。"""
    from src.config import Config
    from src.scout.models import Candidate, Opportunity, Score
    from src.scout.runner import ScoutPipeline

    pipeline = ScoutPipeline(Config.load())
    monkeypatch.setattr(pipeline.niches, "path", tmp_path / "niches.yaml")
    monkeypatch.setattr(pipeline.ledger, "path", tmp_path / "ledger.jsonl")

    low = Opportunity(id="low", candidate=Candidate(title="スコアの低いネタ"),
                      score=Score(scored=True), verdict="watch")
    monkeypatch.setattr(pipeline.store, "get", lambda _id: low)
    monkeypatch.setattr(pipeline.store, "set_status", lambda *a, **k: None)

    reply = pipeline.adopt("low")

    assert CHEAP_TEST in reply
    assert OBSERVE not in reply
    assert pipeline.niches.load()[0].commitment == CHEAP_TEST
