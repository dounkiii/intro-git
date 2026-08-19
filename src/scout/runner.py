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
from .explore import allocate
from .ledger import ExperimentLedger
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
        self.explore_ratio = float(scout.get("explore_ratio", 0.2))

        self.sources = [XApiSource(self.config), GrokSource(self.config)]
        self.store = OpportunityStore()
        self.niches = NicheRegistry()
        self.researcher = Researcher(self.config)
        # 収益実績による加点は行わない（勝っている市場ばかり再発見するループを避けるため）。
        # 実績は explore/exploit の枠配分と Experiment Ledger の側で使う。
        self.scorer = Scorer(self.config, llm=self.researcher.llm)
        self.ledger = ExperimentLedger(funnel_thresholds=scout.get("funnel"))

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

        # 調査枠を exploit（採用済みニッチの深掘り）と explore（新規開拓）に分ける。
        # 採用ニッチが0件のうちは全枠が explore になるので、初動を邪魔しない。
        adopted_texts = [f"{n.label} {n.query}" for n in self.niches.load() if n.active]
        selected = allocate(fresh, adopted_texts, self.research_limit, self.explore_ratio)

        opportunities: list[Opportunity] = []
        for candidate, times_seen in selected:
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

        # 予測を凍結する。以後書き換えないので、後から「予測が当たったか」を検証できる。
        self.ledger.record_prediction(opportunity, niche.slug)
        self.ledger.record_attention("adopt", niche.slug)

        return "\n".join([
            f"✅ `{opportunity_id}` を採用しました。",
            f"　ニッチ: `{niche.slug}` — {niche.label}",
            f"　検索クエリ: `{niche.query}`",
            f"　最初に作るもの: {niche.best_product or '（未検討）'}",
            f"　予測: 機会{opportunity.score.opportunity} "
            f"(発見{opportunity.score.discovery} / 収益{opportunity.score.business})"
            f" 実測率{opportunity.score.observed_ratio:.0%}",
            "",
            "翌朝の生成ジョブからこのテーマで台本と記事が作られます。",
            f"実績は `/metrics {niche.slug} posts=8 impressions=4000 clicks=20` で記録してください。",
        ])

    def drop(self, opportunity_id: str) -> str:
        if self.store.get(opportunity_id) is None:
            return f"⚠️ `{opportunity_id}` が見つかりません。"
        self.store.set_status(opportunity_id, "dropped")
        self.niches.deactivate(opportunity_id)
        self.ledger.record_attention("drop", opportunity_id)
        return f"🗑 `{opportunity_id}` を捨てました。今後は再提示されません。"

    # ------------------------------------------------------------------
    def record_metrics(self, niche_slug: str, values: dict[str, int]) -> str:
        """`/metrics` から実績を記録し、ファネル段階を診断して返す。

        インプ・CTR・CV は各プラットフォームと ASP の管理画面にしか無く、API 連携は
        審査が重い。まずは週1回スマホから手入力する形で、Stage の切り分けだけ先に
        できるようにしている。
        """
        from .funnel import FunnelMetrics

        known = {n.slug for n in self.niches.load()}
        if niche_slug not in known:
            return (f"⚠️ `{niche_slug}` は採用済みニッチにありません。"
                    f"候補: {', '.join(sorted(known)) or '（なし）'}")

        metrics = FunnelMetrics(
            niche=niche_slug,
            posts=values.get("posts", 0),
            impressions=values.get("impressions", 0),
            engaged=values.get("engaged", values.get("views", 0)),
            cta_clicks=values.get("clicks", values.get("cta_clicks", 0)),
            conversions=values.get("conversions", values.get("cv", 0)),
            revenue_jpy=values.get("revenue", 0),
            attention_minutes=self.ledger.attention_minutes(niche_slug),
            api_cost_jpy=values.get("cost", 0),
        )
        outcome = self.ledger.record_outcome(metrics)
        self.ledger.record_attention("metrics", niche_slug)

        verdict = self.ledger.diagnoser.diagnose(metrics)
        lines = [
            f"📊 `{niche_slug}` の実績を記録しました。",
            "",
            f"**Stage {outcome.stage}: {outcome.stage_label}**",
            f"→ {verdict.prescription}",
            "",
            f"- 判定可能か: {'はい' if verdict.decided else 'いいえ（試行回数が不足）'}",
            f"- {verdict.reason}",
            f"- 1投稿あたりインプ: {verdict.metrics['impressions_per_post']:.0f}",
            f"- 反応率: {verdict.metrics['engagement_rate']:.2%} / "
            f"CTR: {verdict.metrics['ctr']:.2%} / CVR: {verdict.metrics['cvr']:.1%}",
            f"- RPM: {verdict.metrics['rpm']:.0f}円 / EPC: {verdict.metrics['epc']:.0f}円",
            f"- 判断1分あたり収益: {verdict.metrics['revenue_per_attention_minute']:.0f}円/分",
        ]
        if verdict.should_exit:
            lines += ["", f"🛑 **撤退を検討**: `/drop <opportunity_id>` でこのニッチを止められます。"]
        return "\n".join(lines)

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
