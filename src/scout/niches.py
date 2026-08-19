"""採用ニッチの管理。探索レイヤと制作レイヤをつなぐ唯一の接点。

ちゃっぴー案の最大の弱点は、発掘して TOP3 を出すところで止まっていること。
情報収集システムは「毎日候補が出てくるが何も作られない」で必ず死ぬ。
そこで `/adopt <id>` で採用したネタをここに書き込み、既存の制作パイプライン
（収集→台本→記事→承認→投稿）がこのファイルを読んでクエリに使う。

これで リサーチ → 制作 → 投稿 → 収益ログ → スコアへの反映 が閉じる。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..config import DATA_DIR
from .commitment import ADOPT, EXIT, OBSERVE, budget_for
from .models import Opportunity

logger = logging.getLogger(__name__)

NICHES_PATH = DATA_DIR / "adopted_niches.yaml"


@dataclass
class Niche:
    """制作パイプラインが1カテゴリとして扱う採用済みニッチ。"""

    slug: str
    label: str
    query: str
    opportunity_id: str = ""
    best_product: str = ""
    monetization_paths: list[str] = field(default_factory=list)
    adopted_at: str = ""
    active: bool = True
    # 投資レベル（src/scout/commitment.py）。ラベルではなく生成枠に効く。
    commitment: str = ADOPT
    creatives_tried: int = 0     # 同ニッチで試した切り口の数。撤退判断に使う
    level_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "slug": self.slug, "label": self.label, "query": self.query,
            "opportunity_id": self.opportunity_id, "best_product": self.best_product,
            "monetization_paths": self.monetization_paths,
            "adopted_at": self.adopted_at, "active": self.active,
            "commitment": self.commitment, "creatives_tried": self.creatives_tried,
            "level_reason": self.level_reason,
        }

    @property
    def items_per_run(self) -> int:
        """1回の生成で作る本数の上限。CHEAP_TEST は小さく、SCALE は大きく。"""
        return budget_for(self.commitment).items_per_run

    @property
    def test_posts(self) -> int:
        """このレベルで公開する上限（0 = 上限なし）。"""
        return budget_for(self.commitment).test_posts


class NicheRegistry:
    def __init__(self, path: Path = NICHES_PATH):
        self.path = path

    def load(self) -> list[Niche]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return [Niche(**entry) for entry in (raw.get("niches") or [])]

    def save(self, niches: list[Niche]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump({"niches": [n.to_dict() for n in niches]},
                           allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def active_queries(self) -> dict[str, str]:
        """制作パイプラインが使う {カテゴリ名: 検索クエリ}。

        生成枠が 0 のレベル（OBSERVE / EXIT）はクエリを出さない。
        """
        return {n.slug: n.query for n in self.load()
                if n.active and n.query and n.items_per_run > 0}

    def item_caps(self) -> dict[str, int]:
        """{カテゴリ名: 1回の生成で作る本数の上限}。投資レベルがここで効く。"""
        return {n.slug: n.items_per_run for n in self.load()
                if n.active and n.items_per_run > 0}

    # ------------------------------------------------------------------
    def adopt(self, opportunity: Opportunity, commitment: str = ADOPT,
              reason: str = "") -> Niche:
        """機会を採用してニッチ化する。既に採用済みならレベルだけ更新する。"""
        niches = self.load()
        existing = next((n for n in niches if n.opportunity_id == opportunity.id), None)
        if existing:
            existing.active = True
            existing.commitment = commitment
            existing.level_reason = reason or existing.level_reason
            self.save(niches)
            logger.info("採用済みのニッチを更新しました: %s (%s)", existing.slug, commitment)
            return existing

        niche = Niche(
            slug=f"adopted_{opportunity.id}",
            label=opportunity.candidate.title[:60],
            query=self.build_query(opportunity),
            opportunity_id=opportunity.id,
            best_product=opportunity.research.best_product,
            monetization_paths=opportunity.research.monetization_paths,
            adopted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            commitment=commitment,
            level_reason=reason,
        )
        niches.append(niche)
        self.save(niches)
        logger.info("ニッチを採用しました: %s (%s / %s)", niche.slug, niche.label, commitment)
        return niche

    def set_commitment(self, niche_slug: str, level: str, reason: str = "") -> Niche | None:
        """投資レベルを更新する。EXIT なら無効化する。"""
        niches = self.load()
        target = next((n for n in niches if n.slug == niche_slug), None)
        if target is None:
            return None
        if target.commitment != level:
            logger.info("投資レベルを変更: %s %s -> %s (%s)",
                        niche_slug, target.commitment, level, reason)
        target.commitment = level
        target.level_reason = reason
        if level in (EXIT, OBSERVE):
            target.active = False
        self.save(niches)
        return target

    def count_creative(self, niche_slug: str) -> int:
        """このニッチで試した切り口の数を1つ増やす。撤退判断に使う。"""
        niches = self.load()
        target = next((n for n in niches if n.slug == niche_slug), None)
        if target is None:
            return 0
        target.creatives_tried += 1
        self.save(niches)
        return target.creatives_tried

    def deactivate(self, opportunity_id: str) -> bool:
        niches = self.load()
        target = next((n for n in niches if n.opportunity_id == opportunity_id), None)
        if target is None:
            return False
        target.active = False
        self.save(niches)
        return True

    @staticmethod
    def build_query(opportunity: Opportunity) -> str:
        """キーワードから X API の検索クエリを組む。

        キーワードが1つも無い場合はタイトルの先頭語を使う。クエリが空だと
        制作パイプラインが空回りするため、必ず何かを返す。
        """
        keywords = [k.strip() for k in opportunity.candidate.keywords if k.strip()]
        # 発掘元の内部ラベル（needs/wants 等）はクエリに使えないので落とす
        keywords = [k for k in keywords if not k.isascii() or len(k) > 3][:4]
        if not keywords:
            keywords = [opportunity.candidate.title.split()[0][:20]]
        terms = " OR ".join(keywords)
        return f"({terms}) lang:ja -is:retweet"
