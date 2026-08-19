"""重複統合・永続化・ニッチ採用のテスト。

「同じネタを毎日見せない」かつ「何日も出続けているネタの伸びを追う」の両立が
このレイヤの要件なので、単純な捨て処理になっていないことを検証する。
"""
from __future__ import annotations

from src.scout.models import Candidate, Opportunity, Research, Score
from src.scout.niches import NicheRegistry
from src.scout.store import OpportunityStore


def _candidate(title: str, keywords: list[str], **signals) -> Candidate:
    return Candidate(title=title, keywords=keywords, source="x_api", signals=signals)


def test_同じネタは統合され観測回数が増える(tmp_path):
    store = OpportunityStore(tmp_path)
    c = _candidate("AI議事録ツールが日本語対応", ["AI議事録", "文字起こし"], likes_per_hour=10)
    store.upsert(Opportunity(id=c.slug, candidate=c))

    fresh, touched = store.merge([c])

    assert len(fresh) == 1
    assert fresh[0][1] == 2                     # times_seen が 2 になっている
    assert touched[0].times_seen == 2


def test_捨てたネタは再提示されない(tmp_path):
    store = OpportunityStore(tmp_path)
    c = _candidate("しょうもないネタ", ["ゴミ"])
    store.upsert(Opportunity(id=c.slug, candidate=c, verdict="drop", status="dropped"))

    fresh, touched = store.merge([c])

    assert fresh == []                          # 調査対象に入らない
    assert touched[0].times_seen == 2           # 観測はされている


def test_表記の違うネタも類似で統合される(tmp_path):
    store = OpportunityStore(tmp_path)
    first = _candidate("インボイスの2割特例が終了する", ["インボイス", "2割特例"])
    store.upsert(Opportunity(id=first.slug, candidate=first))

    second = _candidate("2割特例の終了でインボイス対応が必要", ["インボイス", "2割特例"])
    fresh, _ = store.merge([second], similarity=0.5)

    assert len(fresh) == 1
    assert fresh[0][1] == 2                     # 別タイトルでも同一ネタと判定


def test_無関係なネタは統合されない(tmp_path):
    store = OpportunityStore(tmp_path)
    store.upsert(Opportunity(id="x", candidate=_candidate("インボイス", ["インボイス"])))

    fresh, _ = store.merge([_candidate("ふるさと納税の上限", ["ふるさと納税"])])

    assert len(fresh) == 1
    assert fresh[0][1] == 1                     # 新規扱い


def test_同一実行内の重複は1件になる(tmp_path):
    store = OpportunityStore(tmp_path)
    c = _candidate("同じネタ", ["同じ"])

    fresh, _ = store.merge([c, c, c])

    assert len(fresh) == 1


def test_新しい根拠URLは既存ネタに追記される(tmp_path):
    store = OpportunityStore(tmp_path)
    first = Candidate(title="ネタ", keywords=["k"], evidence_urls=["https://a"])
    store.upsert(Opportunity(id=first.slug, candidate=first))

    store.merge([Candidate(title="ネタ", keywords=["k"], evidence_urls=["https://b"])])

    saved = store.load_all()[0]
    assert saved.candidate.evidence_urls == ["https://a", "https://b"]


def test_保存と読み込みで内容が保たれる(tmp_path):
    store = OpportunityStore(tmp_path)
    o = Opportunity(
        id="abc", candidate=_candidate("ネタ", ["k"]),
        research=Research(why_now="いま", measured={"competitor_domains": 3}),
        score=Score(demand=15, scored=True), verdict="now", action="やる")
    store.upsert(o)

    loaded = store.get("abc")
    assert loaded.research.why_now == "いま"
    assert loaded.research.measured["competitor_domains"] == 3
    assert loaded.score.demand == 15
    assert loaded.verdict == "now"


# --- ニッチ採用 -------------------------------------------------------------
def test_採用でニッチと検索クエリが作られる(tmp_path):
    registry = NicheRegistry(tmp_path / "niches.yaml")
    o = Opportunity(id="abc",
                    candidate=_candidate("インボイス対応の需要", ["インボイス", "会計ソフト"]),
                    research=Research(best_product="比較記事"))

    niche = registry.adopt(o)

    assert niche.slug == "adopted_abc"
    assert "インボイス" in niche.query and "lang:ja" in niche.query
    assert registry.active_queries() == {"adopted_abc": niche.query}


def test_採用は冪等(tmp_path):
    registry = NicheRegistry(tmp_path / "niches.yaml")
    o = Opportunity(id="abc", candidate=_candidate("ネタ", ["k1"]))

    registry.adopt(o)
    registry.adopt(o)

    assert len(registry.load()) == 1


def test_無効化するとクエリから消える(tmp_path):
    registry = NicheRegistry(tmp_path / "niches.yaml")
    registry.adopt(Opportunity(id="abc", candidate=_candidate("ネタ", ["キーワード"])))

    assert registry.deactivate("abc") is True
    assert registry.active_queries() == {}


def test_キーワードが空でもクエリが作られる(tmp_path):
    """クエリが空だと制作パイプラインが空回りするので、必ず何かを返す必要がある。"""
    registry = NicheRegistry(tmp_path / "niches.yaml")
    niche = registry.adopt(Opportunity(id="abc", candidate=Candidate(title="見出しだけ")))

    assert niche.query.strip() != ""
    assert "lang:ja" in niche.query
