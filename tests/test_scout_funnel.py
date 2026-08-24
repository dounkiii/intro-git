"""ファネル段階判定と撤退基準のテスト。

「30日で収益0なら撤退」ではなく「十分な試行回数に達したら段階で切り分ける」
という要件を固定する。100インプで0円と10万インプで0円を区別できること。
"""
from __future__ import annotations

from src.scout.funnel import FunnelDiagnoser, FunnelMetrics


def _d() -> FunnelDiagnoser:
    return FunnelDiagnoser()


def test_指標が未入力ならStage0で前に進める():
    """views 未入力を「Stage1 = ニッチが悪い」と誤診断すると良いニッチを捨てる。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, revenue_jpy=3200))

    assert verdict.stage == 0
    assert verdict.label == "判定不能"
    assert verdict.should_exit is False
    assert "3,200円 は記録済み" in verdict.reason


def test_収益だけでも記録できる():
    """完璧な台帳より続く台帳。revenue 1つでも受け付ける。"""
    m = FunnelMetrics("n", revenue_jpy=3200)

    assert m.has_core is False
    assert _d().diagnose(m).stage == 0


def test_反応系が未入力なら悪いと読み替えない():
    """取れていないことを『刺さっていない』と解釈すると誤診断になる。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, impressions=5000))

    assert verdict.stage == 0                    # Stage2 にはしない
    assert verdict.metrics["engagement_rate"] is None


def test_試行回数が足りなければ判定しない():
    """少ない試行で撤退させないための安全装置。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=2, impressions=100))

    assert verdict.decided is False
    assert verdict.should_exit is False          # Stage1 でも撤退させない
    assert "まだ判定しない" in verdict.prescription


def test_配信されないだけではニッチ撤退にしない():
    """Stage は症状の診断であって原因の断定ではない。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, impressions=300),
                            creatives_tried=1)

    assert verdict.stage == 1
    assert verdict.decided is True
    assert verdict.likely_cause == "creative"
    assert verdict.should_exit is False          # ニッチを捨てない
    assert verdict.retry_creative is True        # 切り口を変えて再試行


def test_複数の切り口で配信されなければニッチ原因と判断する():
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, impressions=300),
                            creatives_tried=3)

    assert verdict.likely_cause == "niche"
    assert verdict.should_exit is True


def test_他ニッチも同程度に低ければ制作側を疑う():
    """同フォーマットで他ニッチも伸びていないなら、原因はニッチではない。"""
    d = FunnelDiagnoser(peer_samples={"other_a": 40.0, "other_b": 35.0})

    verdict = d.diagnose(FunnelMetrics("n", posts=10, impressions=300),
                         creatives_tried=3)

    assert verdict.likely_cause == "creative"
    assert verdict.should_exit is False


def test_他ニッチが好調ならニッチ側が疑わしい():
    d = FunnelDiagnoser(peer_samples={"other_a": 3000.0, "other_b": 2500.0})

    verdict = d.diagnose(FunnelMetrics("n", posts=10, impressions=300),
                         creatives_tried=3)

    assert verdict.likely_cause == "niche"
    assert verdict.should_exit is True
    assert "他ニッチ中央値" in verdict.cause_reason


def test_配信されている段階では原因が段階ごとに変わる():
    d = _d()

    stage2 = d.diagnose(FunnelMetrics("n", posts=10, impressions=5000, engaged=20))
    stage3 = d.diagnose(FunnelMetrics("n", posts=10, impressions=5000,
                                      engaged=300, cta_clicks=5))
    stage4 = d.diagnose(FunnelMetrics("n", posts=10, impressions=5000,
                                      engaged=300, cta_clicks=60, conversions=0))

    assert (stage2.likely_cause, stage3.likely_cause, stage4.likely_cause) == \
("creative", "funnel", "offer")


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


def test_Coreだけで売上があればStage5と判定できる():
    """clicks や CV が無くても、売れている事実は判定できる。"""
    verdict = _d().diagnose(FunnelMetrics("n", posts=10, impressions=5000, revenue_jpy=3200))

    assert verdict.stage == 5


# --- プラットフォーム別と自アカウントbaseline ---------------------------------
def test_プラットフォームごとに配信の下限が変わる():
    """Shorts はサムネ表示と実視聴の差が大きいので下限が高い。"""
    tiktok = FunnelDiagnoser(platform="tiktok").distribution_floor()[0]
    shorts = FunnelDiagnoser(platform="youtube_shorts").distribution_floor()[0]
    x = FunnelDiagnoser(platform="x").distribution_floor()[0]

    assert tiktok < shorts < x


def test_自アカウントの実績が世間の既定値より優先される():
    d = FunnelDiagnoser(baseline_samples=[1000.0] * 12)

    floor, basis = d.distribution_floor()

    assert basis == "own_baseline"
    assert floor == 300.0                        # 中央値の30%
    assert d.diagnose(FunnelMetrics("n", posts=10, impressions=2000)).stage == 1


def test_サンプルが少なければ既定値にフォールバックする():
    d = FunnelDiagnoser(baseline_samples=[1000.0] * 3)

    assert d.baseline is None
    assert d.distribution_floor()[1] == "platform_default"


def test_設定のnullはプラットフォーム既定を消さない():
    d = FunnelDiagnoser({"min_posts": None, "min_impressions": None}, platform="x")

    assert d.min_posts == 15                     # x の既定値が残る


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
    assert m.revenue_per_post == 640.0
    assert m.revenue_per_attention_minute == 200.0


def test_閾値を上げれば判定が保留される():
    """実績分布が見えてきたら config で厳しくできること。"""
    strict = FunnelDiagnoser({"min_posts": 50, "min_impressions": 100000})

    assert strict.diagnose(FunnelMetrics("n", posts=10, impressions=300)).decided is False


def test_換金経路が未提携ならStage4を案件のせいにしない():
    """提携審査が通るまではクリックが出ても成約は起こり得ない。
    「案件を変える」は変える案件が無いので実行できない指示になる。"""
    from src.scout.funnel import (CAUSE_NOT_MONETIZED, CAUSE_OFFER,
                                  FunnelDiagnoser, FunnelMetrics)

    m = FunnelMetrics(niche="n", posts=10, impressions=20000, revenue_jpy=0,
                      engaged=2000, cta_clicks=200, conversions=0,
                      direct_route=False)
    verdict = FunnelDiagnoser().diagnose(m, creatives_tried=2)

    assert verdict.stage == 4
    assert verdict.likely_cause == CAUSE_NOT_MONETIZED
    assert verdict.likely_cause != CAUSE_OFFER
    assert "提携" in verdict.prescription


def test_換金経路があればStage4は案件の問題と診断する():
    from src.scout.funnel import CAUSE_OFFER, FunnelDiagnoser, FunnelMetrics

    m = FunnelMetrics(niche="n", posts=10, impressions=20000, revenue_jpy=0,
                      engaged=2000, cta_clicks=200, conversions=0,
                      direct_route=True)
    verdict = FunnelDiagnoser().diagnose(m, creatives_tried=2)

    assert verdict.stage == 4
    assert verdict.likely_cause == CAUSE_OFFER


def test_換金経路が未提携でも生成枠を絞らない():
    """配信もクリックも成立している唯一のニッチを、オーナー側の
    提携作業待ちで減速させてはいけない。"""
    from src.scout.commitment import ADOPT, next_level
    from src.scout.funnel import CAUSE_NOT_MONETIZED

    level, why, diagnosing = next_level(
        ADOPT, stage=4, decided=True, revenue_jpy=0, posts=10,
        creatives_tried=2, likely_cause=CAUSE_NOT_MONETIZED)

    assert level == ADOPT
    assert diagnosing == ""      # 診断中にしない = 生成枠を絞らない
    assert "判定不能" in why


def test_換金経路が未提携でも撤退はしない():
    """収益0を「このニッチは売れない」という教師データにしない。"""
    from src.scout.commitment import ADOPT, EXIT, next_level
    from src.scout.funnel import CAUSE_NOT_MONETIZED

    level, _, _ = next_level(
        ADOPT, stage=4, decided=True, revenue_jpy=0, posts=50,
        creatives_tried=5, likely_cause=CAUSE_NOT_MONETIZED)

    assert level != EXIT
