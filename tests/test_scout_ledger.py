"""Experiment Ledger のテスト。

要件は2つ。予測行が絶対に書き換わらないこと（さもないと予測の検証にならない）と、
校正がデータ不足のうちは始まらないこと（人間が先に正解を決めない）。
"""
from __future__ import annotations

from src.scout.funnel import FunnelMetrics
from src.scout.ledger import CALIBRATION_MIN_ROWS, ExperimentLedger
from src.scout.models import Candidate, Opportunity, Score


def _opportunity(oid: str = "abc") -> Opportunity:
    return Opportunity(
        id=oid, candidate=Candidate(title="インボイス需要", keywords=["インボイス"]),
        score=Score(demand=18, low_competition=12, monetizability=16, trend_growth=12,
                    contentability=8, affiliate_fit=8, durability=4,
                    source_reliability=4, scored=True, route_available=True,
                    rationale="需要が立ち上がっている"),
        action="比較記事を1本書く")


def test_予測は凍結され上書きされない(tmp_path):
    ledger = ExperimentLedger(tmp_path)
    o = _opportunity()

    first = ledger.record_prediction(o, "adopted_abc")
    o.score.demand = 1                      # あとからスコアを下げても…
    ledger.record_prediction(o, "adopted_abc")

    rows = ledger.rows("prediction")
    assert len(rows) == 1                                   # 追記されない
    assert rows[0]["predicted_total"] == first.predicted_total   # 値も変わらない


def test_予測に検証用の項目が揃っている(tmp_path):
    p = ExperimentLedger(tmp_path).record_prediction(_opportunity(), "adopted_abc")

    assert p.predicted_opportunity > 0
    assert p.predicted_llm_total > 0        # 実測導入の効果を測るため並列保持
    assert p.mapping_version                # 換算ルールの版が入っている
    assert p.why_adopted == "需要が立ち上がっている"
    assert p.expected_action == "比較記事を1本書く"


def test_実績を追記すると段階が判定される(tmp_path):
    ledger = ExperimentLedger(tmp_path)

    outcome = ledger.record_outcome(
        FunnelMetrics("adopted_abc", posts=10, impressions=300))

    assert outcome.stage == 1
    assert outcome.decided is True
    assert ledger.latest_outcome("adopted_abc")["stage"] == 1


def test_実績は何度でも追記され最新が有効(tmp_path):
    ledger = ExperimentLedger(tmp_path)
    ledger.record_outcome(FunnelMetrics("n", posts=10, impressions=300))
    ledger.record_outcome(FunnelMetrics("n", posts=20, impressions=9000, engaged=500,
                                        cta_clicks=100, conversions=2, revenue_jpy=6400))

    assert len(ledger.rows("outcome")) == 2
    assert ledger.latest_outcome("n")["stage"] == 5


def test_判断時間が積算される(tmp_path):
    ledger = ExperimentLedger(tmp_path)
    ledger.record_attention("adopt", "n")          # 90秒
    ledger.record_attention("approve", "n")        # 40秒
    ledger.record_attention("approve", "other")    # 別ニッチ

    assert ledger.attention_minutes("n") == 2.2
    assert ledger.attention_minutes() > ledger.attention_minutes("n")


def test_判断1分あたり収益がレポートに出る(tmp_path):
    ledger = ExperimentLedger(tmp_path)
    ledger.record_prediction(_opportunity(), "adopted_abc")
    ledger.record_attention("adopt", "adopted_abc")
    ledger.record_outcome(FunnelMetrics("adopted_abc", posts=10, impressions=5000,
                                        engaged=300, cta_clicks=60, conversions=2,
                                        revenue_jpy=6400, attention_minutes=1.5))

    report = ledger.render_report()

    assert "判断1分あたり収益" in report
    assert "目的関数" in report


def test_件数が足りないうちは校正を始めない(tmp_path):
    ledger = ExperimentLedger(tmp_path)
    ledger.record_prediction(_opportunity(), "adopted_abc")

    report = ledger.render_report()

    assert f"採用 {CALIBRATION_MIN_ROWS} 件以降" in report
    assert "並列で貯める" in report


def test_予測と実績が対応した行だけ校正表に出る(tmp_path):
    ledger = ExperimentLedger(tmp_path)
    ledger.record_prediction(_opportunity("with"), "niche_with")
    ledger.record_prediction(_opportunity("without"), "niche_without")
    ledger.record_outcome(FunnelMetrics("niche_with", posts=10, impressions=5000,
                                        engaged=300, cta_clicks=60, conversions=1,
                                        revenue_jpy=3200))

    table = ledger.calibration_table()

    assert [r["niche"] for r in table] == ["niche_with"]
    assert table[0]["actual_rpm"] == 640.0
    assert table[0]["actual_stage"] == 5
