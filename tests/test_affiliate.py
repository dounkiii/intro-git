"""収益化レイヤのテスト。

「換金経路のないコンテンツを作らない」が設計上の要なので、経路の解決と
PR表記（ステマ規制対応）の付与を重点的に検証する。
"""
from __future__ import annotations

from src.config import Config
from src.monetize.affiliate import AffiliateEngine


def _config() -> Config:
    return Config.load()


def test_未設定のスロットはスキップされる(monkeypatch):
    monkeypatch.delenv("AFF_ACCOUNTING_SOFT", raising=False)
    monkeypatch.delenv("AFF_TAX_ADVISOR", raising=False)
    monkeypatch.delenv("AFF_HUB_URL", raising=False)
    monkeypatch.delenv("AFF_PRODUCT_URL", raising=False)

    block = AffiliateEngine(_config()).build("tax")

    assert block.offers == []
    assert block.has_route is False
    assert block.route_summary == "なし"


def test_設定済みのスロットだけが解決される(monkeypatch):
    monkeypatch.setenv("AFF_ACCOUNTING_SOFT", "https://example.com/soft")
    monkeypatch.delenv("AFF_TAX_ADVISOR", raising=False)
    monkeypatch.delenv("AFF_HUB_URL", raising=False)
    monkeypatch.delenv("AFF_PRODUCT_URL", raising=False)

    block = AffiliateEngine(_config()).build("tax")

    assert [o.slot for o in block.offers] == ["AFF_ACCOUNTING_SOFT"]
    assert block.offers[0].url == "https://example.com/soft"
    assert block.has_route is True


def test_案件がなくてもハブがあれば経路ありと判定される(monkeypatch):
    for slot in ("AFF_ACCOUNTING_SOFT", "AFF_TAX_ADVISOR", "AFF_PRODUCT_URL"):
        monkeypatch.delenv(slot, raising=False)
    monkeypatch.setenv("AFF_HUB_URL", "https://example.com/links")

    block = AffiliateEngine(_config()).build("tax")

    assert block.has_route is True
    assert "AFF_HUB_URL" in block.route_summary


def test_記事CTAにPR表記と免責が入る(monkeypatch):
    monkeypatch.setenv("AFF_ACCOUNTING_SOFT", "https://example.com/soft")
    engine = AffiliateEngine(_config())
    block = engine.build("tax")

    cta = engine.article_cta_section(block)

    assert "https://example.com/soft" in cta
    assert "PR" in cta                    # ステマ規制（景表法）対応
    assert "一次情報" in cta              # 免責


def test_換金経路がなければCTAは空になる(monkeypatch):
    for slot in ("AFF_ACCOUNTING_SOFT", "AFF_TAX_ADVISOR", "AFF_HUB_URL", "AFF_PRODUCT_URL"):
        monkeypatch.delenv(slot, raising=False)
    engine = AffiliateEngine(_config())

    assert engine.article_cta_section(engine.build("tax")) == ""


def test_動画説明文はリンクを1本に絞る(monkeypatch):
    monkeypatch.setenv("AFF_HUB_URL", "https://example.com/links")
    monkeypatch.setenv("AFF_ACCOUNTING_SOFT", "https://example.com/soft")
    engine = AffiliateEngine(_config())
    block = engine.build("tax")

    footer = engine.video_description_footer(block)

    # 動画の説明欄はリンクが機能しにくいので集約ページのみを載せる
    assert "https://example.com/links" in footer
    assert "https://example.com/soft" not in footer
