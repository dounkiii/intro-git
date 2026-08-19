"""ファネル段階判定と撤退基準のテスト。

「30日で収益0なら撤退」ではなく「十分な試行回数に達したら段階で切り分ける」
という要件を固定する。100インプで0円と10万インプで0円を区別できること。
"""
from __future__ import annotations

from src.scout.funnel import FunnelDiagnoser, FunnelMetrics


def _d() -> FunnelDiagnoser:
    return FunnelDiagnoser()


def test_試行回数が足りなければ判定しない():
    """少ない試行で撤退させないための安全装置。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=2, impressions=100))

    assert verdict.decided is False
    assert verdict.should_exit is False          # Stage1 でも撤退させない
    assert "まだ判定しない" in verdict.prescription


def test_配信されないならStage1で撤退候補():
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, impressions=300))

    assert verdict.stage == 1
    assert verdict.decided is True
    assert verdict.should_exit is True


def test_見られているが刺さらないならStage2で撤退させない():
    """ニッチが悪いのではなくコンテンツが悪い、を区別できること。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, impressions=5000, engaged=20))

    assert verdict.stage == 2
    assert verdict.should_exit is False


def test_導線が弱いならStage3():
    verdict = _d().diagnose(
        FunnelMetrics("n", posts=10, impressions=5000, engaged=300, cta_clicks=5))

    assert verdict.stage == 3


def test_案件が悪いならStage4():
    verdict = _d().diagnose(
        FunnelMetrics("n", posts=10, impressions=5000, engaged=300, cta_clicks=60))

    assert verdict.stage == 4


def test_売れていればStage5():
    verdict = _d().diagnose(
        FunnelMetrics("n", posts=10, impressions=5000, engaged=300, cta_clicks=60,
                      conversions=2, revenue_jpy=6400))

    assert verdict.stage == 5
    assert verdict.should_exit is False


def test_同じ0円でも露出量で段階が変わる():
    """これが『30日で0円』を使わない理由。"""
    few = _d().diagnose(FunnelMetrics("n", posts=10, impressions=200))
    many = _d().diagnose(
        FunnelMetrics("n", posts=10, impressions=100000, engaged=5000, cta_clicks=800))

    assert few.stage == 1        # 配信されていない → ニッチの問題
    assert many.stage == 4       # 売れていない → 案件の問題


def test_収益は露出量で正規化される():
    m = FunnelMetrics("n", posts=10, impressions=10000, cta_clicks=100,
                      conversions=2, revenue_jpy=6400, attention_minutes=32)

    assert m.rpm == 640.0                        # 1,000インプあたり
    assert m.epc == 64.0                         # 1クリックあたり
    assert m.revenue_per_attention_minute == 200.0


def test_閾値を上げれば判定が保留される():
    """実績分布が見えてきたら config で厳しくできること。"""
    strict = FunnelDiagnoser({"min_posts": 50, "min_impressions": 100000})

    assert strict.diagnose(FunnelMetrics("n", posts=10, impressions=300)).decided is False
