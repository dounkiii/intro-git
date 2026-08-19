"""アフィリエイト CTA の解決と注入。

設計方針（docs/PLAYBOOK.md「8. アフィリエイト・ファースト」）:
  プラットフォーム収益は到達条件が重い（TikTok は1万フォロワー、YouTube Shorts は
  90日1,000万再生）。閾値ゼロで換金できるのはアフィリエイトと自前商品だけなので、
  **換金経路のない成果物は作らない**。このモジュールが各成果物に CTA を強制注入し、
  経路がなければ `has_route=False` を立てて承認画面に警告を出す。

実リンクはリポジトリに置かず、環境変数（GitHub Secrets）から解決する。
空の環境変数を指す案件は自動的にスキップされる。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from ..config import Config

logger = logging.getLogger(__name__)


@dataclass
class Offer:
    """1件のアフィリエイト案件（解決済み）。"""

    slot: str      # 環境変数名
    label: str     # 表示名（例: 確定申告ソフト）
    cta: str       # 誘導文
    url: str       # 解決済み URL


@dataclass
class MonetizationBlock:
    """成果物に差し込む収益化ブロック。"""

    offers: list[Offer]
    hub_url: str
    product_url: str
    disclosure: str
    liability_note: str

    @property
    def has_route(self) -> bool:
        """換金経路が1つでもあるか。false の案件は承認前に警告される。"""
        return bool(self.offers or self.hub_url or self.product_url)

    @property
    def route_summary(self) -> str:
        """承認カードに出す1行サマリ。"""
        if self.offers:
            return " / ".join(f"{o.label} ({o.slot})" for o in self.offers)
        if self.product_url:
            return "自前デジタル商品 (AFF_PRODUCT_URL)"
        if self.hub_url:
            return "リンク集約ページ (AFF_HUB_URL)"
        return "なし"


class AffiliateEngine:
    def __init__(self, config: Config):
        self.config = config
        m = config.section("monetization")
        self.disclosure: str = m.get("disclosure", "")
        self.liability_note: str = m.get("liability_note", "")
        self.offers_by_category: dict[str, list[dict]] = m.get("offers", {}) or {}
        self.hub_url = self._resolve(m.get("hub_url_slot", ""))
        self.product_url = self._resolve(m.get("product_url_slot", ""))

    @staticmethod
    def _resolve(slot: str) -> str:
        """環境変数名からリンクを解決する。未設定なら空文字。"""
        if not slot:
            return ""
        return os.getenv(slot, "").strip()

    def build(self, category: str) -> MonetizationBlock:
        """カテゴリに対応する収益化ブロックを組む。

        探索レイヤで採用した新しいニッチは専用の案件定義を持たないため、
        `offers.default` にフォールバックする。これが無いと採用したネタが
        すべて「換金経路なし」になり、1本も作られなくなる。
        """
        entries = self.offers_by_category.get(category)
        if not entries:
            entries = self.offers_by_category.get("default", []) or []
            if entries:
                logger.debug("category=%s に専用案件がないため default を使います。", category)

        resolved: list[Offer] = []
        for entry in entries:
            slot = entry.get("slot", "")
            url = self._resolve(slot)
            if not url:
                logger.debug("アフィリ案件をスキップ（%s が未設定）: %s", slot, entry.get("label"))
                continue
            resolved.append(
                Offer(slot=slot, label=entry.get("label", slot),
                      cta=entry.get("cta", ""), url=url)
            )

        block = MonetizationBlock(
            offers=resolved,
            hub_url=self.hub_url,
            product_url=self.product_url,
            disclosure=self.disclosure,
            liability_note=self.liability_note,
        )
        if not block.has_route:
            logger.warning(
                "category=%s に換金経路がありません。AFF_* の環境変数を設定してください。", category
            )
        return block

    # ------------------------------------------------------------------
    def video_description_footer(self, block: MonetizationBlock) -> str:
        """動画説明文の末尾。動画の説明欄はリンクが機能しにくいので集約先へ1本に絞る。"""
        lines: list[str] = []
        if block.hub_url:
            lines.append(f"▼詳しい解説と関連リンク\n{block.hub_url}")
        elif block.product_url:
            lines.append(f"▼詳しい解説\n{block.product_url}")
        if block.liability_note:
            lines.append(block.liability_note)
        if block.disclosure and (block.hub_url or block.product_url or block.offers):
            lines.append(block.disclosure)
        return "\n".join(lines)

    def article_cta_section(self, block: MonetizationBlock) -> str:
        """記事末尾の CTA セクション（Markdown）。ここが主な換金ポイント。"""
        if not block.has_route:
            return ""

        parts = ["## 手続きを楽にする手段", ""]
        if block.disclosure:
            parts.extend([block.disclosure, ""])

        for offer in block.offers:
            cta = offer.cta or "詳細はこちら"
            parts.append(f"- **{offer.label}** — {cta}: {offer.url}")

        if block.product_url:
            parts.append(f"- **手順をまとめた資料** — 迷わず進めたい方向け: {block.product_url}")
        if block.hub_url and not block.offers:
            parts.append(f"- **関連リンクまとめ** — {block.hub_url}")

        if block.liability_note:
            parts.extend(["", block.liability_note])
        return "\n".join(parts)
