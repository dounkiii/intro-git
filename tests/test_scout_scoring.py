"""採点と判定のテスト。

このシステムの価値は「LLM の自己申告を実測で殴る」ところにあるので、
補正と矛盾検出、そして順位付けの向きを重点的に検証する。
"""
from __future__ import annotations

from src.config import Config
from src.scout.models import Candidate, Opportunity, Research, Score
from src.scout.scoring import Scorer


def _scorer(**kwargs) -> Scorer:
    class _NoLLM:
        available = False

        def generate_json(self, *a, **k):
            return None

    return Scorer(Config.load(), llm=_NoLLM(), **kwargs)


def _high_score(**overrides) -> Score:
    base = dict(demand=18, low_competition=14, monetizability=18, trend_growth=14,
                contentability=9, affiliate_fit=9, durability=4,
                source_reliability=4, scored=True)
    base.update(overrides)
    return Score(**base)


def test_競合が多いのに競合少と採点したら減点され矛盾が立つ():
    scorer = _scorer()
    score = _high_score()
    candidate = Candidate(title="t", source="grok")
    research = Research(measured={"competitor_domains": 12, "evidence_count": 12})

    scorer._apply_machine_adjustments(score, candidate, research, times_seen=1)

    assert score.machine_adjust == -10
    assert any("独立ドメイン" in c for c in score.conflicts)
    assert score.total < score.llm_total


def test_根拠URLが0件なら減点される():
    scorer = _scorer()
    score = _high_score()

    scorer._apply_machine_adjustments(score, Candidate(title="t", source="grok"),
                                      Research(measured={"competitor_domains": 0,
                                                         "evidence_count": 0}), 1)

    assert score.machine_adjust == -8
    assert any("根拠URL" in c for c in score.conflicts)


def test_伸びが遅いX発掘は減点される():
    scorer = _scorer()
    score = _high_score()
    candidate = Candidate(title="t", source="x_api", signals={"likes_per_hour": 1.0})

    scorer._apply_machine_adjustments(
        score, candidate, Research(measured={"competitor_domains": 2, "evidence_count": 3}), 1)

    assert score.machine_adjust == -5
    assert any("いいね/時間" in r for r in score.adjust_reasons)


def test_急伸しているX発掘は加点される():
    scorer = _scorer()
    score = _high_score()
    candidate = Candidate(title="t", source="x_api", signals={"likes_per_hour": 40.0})

    scorer._apply_machine_adjustments(
        score, candidate, Research(measured={"competitor_domains": 2, "evidence_count": 3}), 1)

    assert score.machine_adjust == 5


def test_何度も出るのに伸びなければ陳腐化として減点される():
    scorer = _scorer()
    score = _high_score()
    candidate = Candidate(title="t", source="grok", signals={"likes_per_hour": 1.0})

    scorer._apply_machine_adjustments(
        score, candidate, Research(measured={"competitor_domains": 2, "evidence_count": 3}), 5)

    assert any("観測されているが伸びていない" in r for r in score.adjust_reasons)


def test_実績のあるキーワードは加点される():
    scorer = _scorer(niche_revenue={"インボイス": 3200})
    score = _high_score()
    candidate = Candidate(title="t", source="grok", keywords=["インボイス"])

    scorer._apply_machine_adjustments(
        score, candidate, Research(measured={"competitor_domains": 2, "evidence_count": 3}), 1)

    assert any("実績" in r for r in score.adjust_reasons)


# --- 判定 -------------------------------------------------------------------
def test_未採点なら捨てる判定にはならない():
    """APIキー未設定で合計0点のときに全件 drop になると、システムが黙って死ぬ。"""
    assert _scorer().decide_verdict(Score(scored=False)) == "watch"


def test_低スコアは捨てる():
    assert _scorer().decide_verdict(Score(demand=5, scored=True)) == "drop"


def test_高スコアかつ早期シグナルが高ければ今すぐ狙う():
    score = _high_score(llm_verdict="now")
    assert _scorer().decide_verdict(score) == "now"


def test_LLMと機械判定が食い違えば保守側を採る():
    # 合計点は高いが LLM 自身が watch と言っている → watch を採る
    score = _high_score(llm_verdict="watch")
    scorer = _scorer()

    assert scorer.decide_verdict(score) == "watch"

    # 逆に LLM が now でも合計点が低ければ drop
    low = Score(demand=4, llm_verdict="now", scored=True)
    assert scorer.decide_verdict(low) == "drop"
    assert any("保守側" in c for c in low.conflicts)


def test_順位付けは合計点より早期シグナルを優先する():
    """すでに大流行しているテーマ（合計高・競合多）を上位に出さないための要件。"""
    crowded = Opportunity(              # 合計は高いが競合だらけ
        id="crowded", candidate=Candidate(title="流行中"),
        score=Score(demand=20, low_competition=1, monetizability=20, trend_growth=15,
                    contentability=10, affiliate_fit=10, durability=5,
                    source_reliability=5, scored=True))
    early = Opportunity(                # 合計は低いが伸び始め＆競合少
        id="early", candidate=Candidate(title="伸び始め"),
        score=Score(demand=10, low_competition=14, monetizability=10, trend_growth=13,
                    contentability=5, affiliate_fit=5, durability=3,
                    source_reliability=3, scored=True))

    assert crowded.score.total > early.score.total          # 合計では流行中が上
    ranked = _scorer().rank([crowded, early])
    assert ranked[0].id == "early"                          # 順位では伸び始めが上
