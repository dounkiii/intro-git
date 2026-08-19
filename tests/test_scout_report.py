"""日次レポートのテスト。人間が読んで判断できる形になっているかを見る。"""
from __future__ import annotations

from src.scout.models import Candidate, Opportunity, Research, Score
from src.scout.report import render_daily_report


def _opportunity(oid: str, title: str, **score_kwargs) -> Opportunity:
    return Opportunity(
        id=oid,
        candidate=Candidate(title=title, summary="概要", source="x_api"),
        research=Research(why_now="いま", target_user="個人事業主",
                          monetization_paths=["アフィリ記事", "有料note"],
                          best_product="比較記事", risks=["一過性"],
                          sources=["https://example.com/a"],
                          measured={"competitor_domains": 3, "evidence_count": 1}),
        score=Score(scored=True, **score_kwargs),
        verdict="now", action="比較記事を1本書く",
    )


def test_候補がなければ原因を提示する():
    report = render_daily_report([], top_n=3)

    assert "候補がありません" in report
    assert "XAI_API_KEY" in report


def test_1位の見出しと必要項目が出る():
    report = render_daily_report([_opportunity("abc", "インボイス需要", demand=18)], top_n=3)

    for expected in ("今日の1位", "インボイス需要", "なぜ今なのか", "想定ユーザー",
                     "収益化方法", "リスク", "機会スコア", "発見スコア", "収益スコア",
                     "実測で埋まった軸", "今やるべきアクション", "/adopt abc"):
        assert expected in report


def test_上位n件だけ詳細表示し残りは畳む():
    items = [_opportunity(f"id{i}", f"ネタ{i}", demand=20 - i) for i in range(6)]

    report = render_daily_report(items, top_n=2)

    assert "第2位" in report
    assert "第3位" not in report
    assert "その他の候補（4件）" in report


def test_未採点は警告が出る():
    o = _opportunity("abc", "ネタ")
    o.score.scored = False

    assert "未採点" in render_daily_report([o], top_n=1)


def test_換金経路がなければ警告が出る():
    o = _opportunity("abc", "ネタ", demand=18)
    o.score.route_available = False

    assert "換金経路なし" in render_daily_report([o], top_n=1)


def test_実測で置き換えた軸が表示される():
    o = _opportunity("abc", "ネタ", demand=18)
    o.score.evidence.observe("low_competition", 15, 3,
                             source="serp_heuristic", confidence=0.45, note="大手多数")

    report = render_daily_report([o], top_n=1)

    assert "実測で置き換えた軸" in report
    assert "serp_heuristic" in report


def test_LLMと実測の食い違いが表示される():
    o = _opportunity("abc", "ネタ", low_competition=14)
    o.score.conflicts.append("LLMは競合が少ないと判断だが独立ドメインが12件")

    report = render_daily_report([o], top_n=1)

    assert "食い違い" in report
    assert "独立ドメインが12件" in report
