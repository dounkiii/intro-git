"""採点と判定のテスト。

このレイヤの価値は「LLM の推測を、測れた分だけ実測で置き換える」ところにある。
置き換えの向き、矛盾の記録、そして順位付けの向きを重点的に検証する。
"""
from __future__ import annotations

from src.config import Config
from src.scout.models import RUBRIC, Candidate, Opportunity, Research, Score
from src.scout.scoring import Scorer


class _NoLLM:
    available = False

    def generate_json(self, *a, **k):
        return None


def _scorer() -> Scorer:
    return Scorer(Config.load(), llm=_NoLLM())


def _high_score(**overrides) -> Score:
    base = dict(demand=18, low_competition=14, monetizability=18, trend_growth=14,
                contentability=9, affiliate_fit=9, durability=4,
                source_reliability=4, scored=True, monetization_observed=True)
    base.update(overrides)
    return Score(**base)


def _research(**measured) -> Research:
    base = {"competitor_domains": 2, "evidence_count": 3, "results": [], "keywords": []}
    base.update(measured)
    return Research(measured=base)


# --- 観測が推測を置き換える -------------------------------------------------
def test_実測は推測に足し引きせず置き換える():
    """旧実装は「矛盾したら -10」だった。実測は補正ではなく置換であるべき。"""
    score = _high_score()
    score.evidence.observe("low_competition", 15, 3, source="serp_heuristic", confidence=0.45)

    assert score.evidence.value("low_competition") == 3       # 14 ではなく 3
    assert score.llm_total == 90                              # 推測の合計は保持される
    assert score.total == 79                                  # 90 - 14 + 3
    assert score.evidence.divergences()["low_competition"] == -11


def test_SERPが弱ければ競合の少なさが実測で上がる():
    """上位が知恵袋・個人ブログばかりなら参入余地あり、と実測される。"""
    scorer = _scorer()
    score = _high_score(low_competition=5)
    weak_serp = [{"url": f"https://detail.chiebukuro.yahoo.co.jp/q{i}", "title": "質問"}
                 for i in range(3)]
    weak_serp += [{"url": f"https://x{i}.hatenablog.com/e", "title": "体験談"} for i in range(2)]

    scorer._observe_competition(score, _research(results=weak_serp))

    ev = score.evidence.items["low_competition"]
    assert ev.is_observed
    assert ev.observed > 5                                    # 推測より高い
    assert ev.source == "serp_heuristic"
    assert ev.confidence <= 0.5                               # 代理指標なので低信頼


def test_SERPが強ければ競合の少なさが実測で下がる():
    scorer = _scorer()
    score = _high_score(low_competition=14)
    strong_serp = [
        {"url": "https://www.nta.go.jp/a", "title": "インボイス制度"},
        {"url": "https://www.nikkei.com/b", "title": "インボイス解説"},
        {"url": "https://freee.co.jp/c", "title": "インボイスとは"},
        {"url": "https://www.amazon.co.jp/d", "title": "インボイス 本"},
        {"url": "https://zeiri4.com/e", "title": "インボイス 税理士"},
    ]

    scorer._observe_competition(score, _research(results=strong_serp, keywords=["インボイス"]))

    assert score.evidence.items["low_competition"].observed < 14
    assert score.total < score.llm_total


def test_サンプルが少なすぎるSERPは採用しない():
    """代理指標を過信しないための安全装置。"""
    scorer = _scorer()
    score = _high_score()

    scorer._observe_competition(score, _research(results=[{"url": "https://a.example", "title": ""}]))

    assert score.evidence.items["low_competition"].is_observed is False
    assert any("SERP判定を採用せず" in n for n in score.notes)


def test_いいね毎時から成長性が実測される():
    scorer = _scorer()
    score = _high_score(trend_growth=5)
    candidate = Candidate(title="t", source="x_api", signals={"likes_per_hour": 40.0})

    scorer._observe_growth(score, candidate, times_seen=1)

    ev = score.evidence.items["trend_growth"]
    assert ev.observed > 5                                    # 推測より高く実測される
    assert ev.source == "x_velocity"
    assert "log換算" in ev.note


def test_成長性の換算は対数で上位を潰さない():
    """SNS指標は 10/20/40/…/10000 と歪むので線形だと上位が飽和し下位が過大になる。"""
    scorer = _scorer()
    points = []
    for velocity in (2, 10, 50, 500):
        score = _high_score()
        scorer._observe_growth(
            score, Candidate(title="t", source="x_api",
                             signals={"likes_per_hour": float(velocity)}), times_seen=1)
        points.append(score.evidence.value("trend_growth"))

    assert points == sorted(points)                # 単調増加
    assert points[0] < points[1] < points[2]       # 低〜中域で差がつく
    # 対数なので 10→50 の伸びより 2→10 の伸びの方が点数差が大きくならない
    assert (points[1] - points[0]) >= (points[3] - points[2])


def test_伸びが遅ければ成長性は低く実測される():
    scorer = _scorer()
    score = _high_score(trend_growth=14)
    candidate = Candidate(title="t", source="x_api", signals={"likes_per_hour": 1.0})

    scorer._observe_growth(score, candidate, times_seen=1)

    assert score.evidence.items["trend_growth"].observed < 5


def test_何度も出るのに伸びなければさらに下がる():
    scorer = _scorer()
    low, stale = _high_score(), _high_score()
    candidate = Candidate(title="t", source="x_api", signals={"likes_per_hour": 4.0})

    scorer._observe_growth(low, candidate, times_seen=1)
    scorer._observe_growth(stale, candidate, times_seen=6)

    assert stale.evidence.value("trend_growth") < low.evidence.value("trend_growth")
    assert "観測されているが伸びていない" in stale.evidence.items["trend_growth"].note


def test_Grok発掘には速度の実測を適用しない():
    """likes_per_hour が取れない発掘元に実測を騙らせない。"""
    scorer = _scorer()
    score = _high_score()

    scorer._observe_growth(score, Candidate(title="t", source="grok"), times_seen=1)

    assert score.evidence.items["trend_growth"].is_observed is False


def test_根拠URLが0件なら信頼性は実測0になる():
    scorer = _scorer()
    score = _high_score()

    scorer._observe_reliability(score, _research(competitor_domains=0, evidence_count=0))

    assert score.evidence.items["source_reliability"].observed == 0
    assert score.total < score.llm_total


def test_大きなズレだけが矛盾として記録される():
    scorer = _scorer()
    score = _high_score(low_competition=14)
    score.evidence.observe("low_competition", 15, 3, source="serp_heuristic", confidence=0.45)
    score.evidence.observe("source_reliability", 5, 4, source="evidence_count", confidence=0.8)

    scorer._record_divergences(score)

    assert len(score.conflicts) == 1                          # 差1点の軸は記録しない
    assert "low_competition" in score.conflicts[0]
    assert "過大評価" in score.conflicts[0]


# --- confidence の扱い ------------------------------------------------------
def test_confidenceは順位スコアに掛けない():
    """早いトレンドほど根拠が薄いので、掛けると成熟したネタを好むシステムになる。"""
    thin = _high_score()                        # 実測ゼロ = 低 confidence
    thick = _high_score()
    for axis, mx in (("low_competition", 15), ("trend_growth", 15)):
        thick.evidence.observe(axis, mx, thick.evidence.value(axis),
                               source="test", confidence=0.9)

    assert thick.confidence > thin.confidence
    assert thin.discovery == thick.discovery    # 順位スコアは confidence に影響されない


def test_高スコアで低確信ならexplore候補として印が付く():
    score = _high_score()

    assert score.confidence < 0.45
    assert score.speculative is True


def test_低確信は今すぐ狙うにはならず様子見になる():
    """順位には効かせないが、本気で投資する判定にはゲートとして使う。"""
    score = _high_score(llm_verdict="now")

    verdict = _scorer().decide_verdict(score)

    assert score.total >= 70 and score.opportunity >= 30
    assert verdict == "watch"
    assert any("根拠が薄い" in n for n in score.notes)


def test_確信が高ければ今すぐ狙うになる():
    score = _high_score(llm_verdict="now")
    for axis, mx in RUBRIC.items():
        score.evidence.observe(axis, mx, score.evidence.value(axis),
                               source="test", confidence=0.8)

    assert _scorer().decide_verdict(score) == "now"


# --- 合成スコア -------------------------------------------------------------
def test_換金の準備度で収益スコアに段階が付く():
    """「AFF_* が無い = 金にならない」と学習させないための3値。"""
    immediate = _high_score(monetization_observed=True)
    potential = _high_score(monetization_observed=False, monetization_inferred=True)
    none = _high_score(monetization_observed=False, monetization_inferred=False)

    assert immediate.business > potential.business > none.business
    assert none.business > 0          # ゼロにはしない（案件は後から開拓できる）


def test_収益化の道が何も挙がらなければnoneになる():
    scorer = _scorer()
    score = _high_score()

    scorer._observe(score, Candidate(title="t", keywords=["まだ案件のないニッチ"]),
                    _research(), 1)

    assert score.monetization_readiness == "none"
    assert score.monetization_source == "none"


def test_機会スコアは片方がゼロなら上がらない():
    """相乗平均なので「入る余地はあるが金にならない」は上位に来ない。"""
    no_business = Score(demand=0, low_competition=15, trend_growth=15,
                        monetizability=0, affiliate_fit=0, contentability=10,
                        durability=5, source_reliability=5, scored=True)
    no_room = Score(demand=20, low_competition=0, trend_growth=0,
                    monetizability=20, affiliate_fit=10, contentability=10,
                    durability=5, source_reliability=5, scored=True,
                    monetization_observed=True)

    assert no_business.opportunity == 0.0
    assert no_room.opportunity == 0.0


def test_実測が増えると信頼度が上がる():
    """信頼度は上がるが、発見スコア（順位）には影響しない。"""
    low_conf = _high_score()
    high_conf = _high_score()
    for axis, mx in (("low_competition", 15), ("trend_growth", 15)):
        high_conf.evidence.observe(axis, mx, high_conf.evidence.value(axis),
                                   source="test", confidence=0.9)

    assert high_conf.confidence > low_conf.confidence
    assert high_conf.discovery == low_conf.discovery


# --- 判定 -------------------------------------------------------------------
def test_未採点なら捨てる判定にはならない():
    """APIキー未設定で0点のときに全件 drop になると、システムが黙って死ぬ。"""
    assert _scorer().decide_verdict(Score(scored=False)) == "watch"


def test_素点が低ければ捨てる():
    assert _scorer().decide_verdict(Score(demand=5, scored=True)) == "drop"


def test_素点が高くても機会スコアが低ければ今すぐ狙わない():
    """素点だけ高い「大流行テーマ」を now にしないための要件。"""
    crowded = Score(demand=20, low_competition=1, monetizability=20, trend_growth=15,
                    contentability=10, affiliate_fit=10, durability=5,
                    source_reliability=5, scored=True, llm_verdict="now",
                    monetization_observed=True)

    assert crowded.total >= 70
    assert _scorer().decide_verdict(crowded) != "now"


def test_LLMと機械判定が食い違えば保守側を採る():
    score = _high_score(llm_verdict="watch")
    assert _scorer().decide_verdict(score) == "watch"

    low = Score(demand=4, llm_verdict="now", scored=True)
    assert _scorer().decide_verdict(low) == "drop"
    assert any("保守側" in c for c in low.conflicts)


def test_順位付けは機会スコアで決まる():
    crowded = Opportunity(          # 素点は満点だが競合だらけ
        id="crowded", candidate=Candidate(title="流行中"),
        score=Score(demand=20, low_competition=1, monetizability=20, trend_growth=15,
                    contentability=10, affiliate_fit=10, durability=5,
                    source_reliability=5, scored=True, monetization_observed=True))
    balanced = Opportunity(         # 素点は低いが両方そこそこ
        id="balanced", candidate=Candidate(title="伸び始め"),
        score=Score(demand=12, low_competition=11, monetizability=12, trend_growth=11,
                    contentability=7, affiliate_fit=7, durability=3,
                    source_reliability=3, scored=True, monetization_observed=True))

    assert crowded.score.total > balanced.score.total
    assert _scorer().rank([crowded, balanced])[0].id == "balanced"
