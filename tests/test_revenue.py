"""投稿ログ・収益ログと週次レポートのテスト。"""
from __future__ import annotations

from src.monetize.revenue import RevenueLog


def test_投稿と収益を集計できる(tmp_path):
    log = RevenueLog(tmp_path)
    log.log_post("tax-1", "tax", "tiktok", "published", "確定申告ソフト", "t1")
    log.log_post("tax-2", "tax", "tiktok", "published", "確定申告ソフト", "t2")
    log.log_post("tax-3", "tax", "-", "rejected", "確定申告ソフト", "t3")
    log.log_revenue(3200, "A8", "確定申告ソフト")
    log.log_revenue(800, "もしも")

    s = log.summarize(days=7)

    assert s.posted == 2
    assert s.rejected == 1
    assert s.revenue_jpy == 4000
    assert s.by_category == {"tax": 2}


def test_換金経路なしをカウントする(tmp_path):
    log = RevenueLog(tmp_path)
    log.log_post("tax-1", "tax", "-", "approved", "なし", "t1")
    log.log_post("tax-2", "tax", "-", "approved", "確定申告ソフト", "t2")

    assert log.summarize().routeless == 1


def test_ログがなくてもレポートを出せる(tmp_path):
    report = RevenueLog(tmp_path).render_report()

    assert "週次レポート" in report
    assert "投稿ゼロ" in report


def test_投稿はあるが収益ゼロだと見直しを促す(tmp_path):
    log = RevenueLog(tmp_path)
    for i in range(12):
        log.log_post(f"tax-{i}", "tax", "tiktok", "published", "確定申告ソフト", "t")

    report = log.render_report()

    assert "収益ゼロ" in report
    assert "CTA" in report


def test_採用0件なら承認が止まっているとは書かない(tmp_path):
    """止まったのではなく、まだ始まっていない。区別しないと誤診断になる。"""
    report = RevenueLog(tmp_path).render_report(adopted=0)

    assert "まだ採用したニッチがない" in report
    assert "承認が止まっている" not in report


def test_採用済みで投稿ゼロなら承認の停止を疑う(tmp_path):
    report = RevenueLog(tmp_path).render_report(adopted=3)

    assert "承認が止まっている" in report
