"""探索パイプラインのオーケストレーション。

  発掘（Grok / X API）→ 重複統合 → 裏取り（Claude + web_search）
  → 採点（Claude + 実測補正）→ 順位付け → 日次レポート Issue

`/adopt` されたネタは data/adopted_niches.yaml に書かれ、翌朝の制作パイプラインが
そのクエリで動き出す。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import Config
from ..monetize.revenue import RevenueLog
from .models import Candidate, Opportunity
from .niches import NicheRegistry
from .report import render_daily_report
from .research import Researcher
from .scoring import Scorer
from .sources import GrokSource, XApiSource
from .store import SCOUT_DIR, OpportunityStore

logger = logging.getLogger(__name__)

SAMPLE_PATH = SCOUT_DIR / "sample_candidates.json"


class ScoutPipeline:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        scout = self.config.section("scout")
        self.discover_limit = int(scout.get("discover_limit", 12))
        self.research_limit = int(scout.get("research_limit", 6))
        self.top_n = int(scout.get("top_n", 3))
        self.similarity = float(scout.get("dedup_similarity", 0.6))

        self.sources = [XApiSource(self.config), GrokSource(self.config)]
        self.store = OpportunityStore()
        self.niches = NicheRegistry()
        self.researcher = Researcher(self.config)
        self.scorer = Scorer(
            self.config,
            llm=self.researcher.llm,
            niche_revenue=RevenueLog().revenue_by_token(),
        )

    # ------------------------------------------------------------------
    def discover(self, use_sample: bool = False) -> list[Candidate]:
        if use_sample:
            return self._sample()

        active = [s for s in self.sources if s.available]
        if not active:
            logger.warning("有効な発掘元がありません。サンプルデータで実行します。"
                           "（X_BEARER_TOKEN / XAI_API_KEY を設定してください）")
            return self._sample()

        candidates: list[Candidate] = []
        for source in active:
            found = source.discover(self.discover_limit)
            logger.info("発掘: %s から %d件", source.name, len(found))
            candidates.extend(found)
        return candidates

    def run(self, use_sample: bool = False, open_issue: bool = False
            ) -> tuple[list[Opportunity], str]:
        """1日分の探索を実行し、(順位付け済みの機会, レポート本文) を返す。"""
        candidates = self.discover(use_sample=use_sample)
        if not candidates:
            return [], render_daily_report([], self.top_n)

        fresh, touched = self.store.merge(candidates, similarity=self.similarity)
        logger.info("重複統合: 調査対象 %d件 / 既存の観測更新 %d件", len(fresh), len(touched))

        if not self.researcher.available:
            logger.warning("ANTHROPIC_API_KEY が未設定です。裏取りと採点は行われません。"
                           "候補の一覧だけが出力されます。")

        # 調査はコストがかかるので、伸びの速い順に上位だけ深掘りする
        fresh.sort(key=lambda pair: pair[0].signals.get("likes_per_hour", 0), reverse=True)

        opportunities: list[Opportunity] = []
        for candidate, times_seen in fresh[: self.research_limit]:
            research = self.researcher.investigate(candidate)
            score, action = self.scorer.score(candidate, research, times_seen)
            verdict = self.scorer.decide_verdict(score)

            opportunity = Opportunity(
                id=candidate.slug, candidate=candidate, research=research,
                score=score, verdict=verdict, action=action, times_seen=times_seen,
                status="dropped" if verdict == "drop" else "new",
            )
            self.store.upsert(opportunity)
            opportunities.append(opportunity)

        # 「捨てる」判定は提示しない（毎日同じゴミを見せないため）
        shown = [o for o in opportunities if o.verdict != "drop"]
        ranked = self.scorer.rank(shown)
        report = render_daily_report(ranked, self.top_n, scanned=len(opportunities))

        if open_issue:
            self._open_issue(report, len(ranked))
        return ranked, report

    # ------------------------------------------------------------------
    def adopt(self, opportunity_id: str) -> str:
        """機会を採用し、制作パイプラインのニッチに登録する。"""
        opportunity = self.store.get(opportunity_id)
        if opportunity is None:
            return f"⚠️ `{opportunity_id}` が見つかりません。"

        niche = self.niches.adopt(opportunity)
        self.store.set_status(opportunity_id, "adopted")
        return "\n".join([
            f"✅ `{opportunity_id}` を採用しました。",
            f"　ニッチ: `{niche.slug}` — {niche.label}",
            f"　検索クエリ: `{niche.query}`",
            f"　最初に作るもの: {niche.best_product or '（未検討）'}",
            "",
            "翌朝の生成ジョブからこのテーマで台本と記事が作られます。",
        ])

    def drop(self, opportunity_id: str) -> str:
        if self.store.get(opportunity_id) is None:
            return f"⚠️ `{opportunity_id}` が見つかりません。"
        self.store.set_status(opportunity_id, "dropped")
        self.niches.deactivate(opportunity_id)
        return f"🗑 `{opportunity_id}` を捨てました。今後は再提示されません。"

    # ------------------------------------------------------------------
    def _open_issue(self, report: str, count: int) -> None:
        from datetime import date

        from ..publishers.github_issue import GitHubIssueSurface

        surface = GitHubIssueSurface(self.config)
        surface.label = self.config.section("scout").get("label", "scout-report")
        surface.create_issue(f"リサーチ結果 {date.today().isoformat()}（{count}件）", report)

    @staticmethod
    def _sample() -> list[Candidate]:
        """API キーなしで全体を動かすためのサンプル候補。"""
        if not SAMPLE_PATH.exists():
            return []
        data = json.loads(Path(SAMPLE_PATH).read_text(encoding="utf-8"))
        return [Candidate(**entry) for entry in data.get("candidates", [])]
