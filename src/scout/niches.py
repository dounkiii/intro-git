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

    def to_dict(self) -> dict:
        return {
            "slug": self.slug, "label": self.label, "query": self.query,
            "opportunity_id": self.opportunity_id, "best_product": self.best_product,
            "monetization_paths": self.monetization_paths,
            "adopted_at": self.adopted_at, "active": self.active,
        }


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
        """制作パイプラインが使う {カテゴリ名: 検索クエリ}。"""
        return {n.slug: n.query for n in self.load() if n.active and n.query}

    # ------------------------------------------------------------------
    def adopt(self, opportunity: Opportunity) -> Niche:
        """機会を採用してニッチ化する。既に採用済みなら再有効化するだけ。"""
        niches = self.load()
        existing = next((n for n in niches if n.opportunity_id == opportunity.id), None)
        if existing:
            existing.active = True
            self.save(niches)
            logger.info("既に採用済みのニッチを再有効化しました: %s", existing.slug)
            return existing

        niche = Niche(
            slug=f"adopted_{opportunity.id}",
            label=opportunity.candidate.title[:60],
            query=self.build_query(opportunity),
            opportunity_id=opportunity.id,
            best_product=opportunity.research.best_product,
            monetization_paths=opportunity.research.monetization_paths,
            adopted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        niches.append(niche)
        self.save(niches)
        logger.info("ニッチを採用しました: %s (%s)", niche.slug, niche.label)
        return niche

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
