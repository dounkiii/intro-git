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
        selected = allocate(fresh, adopted_texts, self.research_limit,
                            self.explore_ratio, winners=self._winner_count())

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

        # explore 枠に相当する「高スコアだが根拠が薄い」候補は、埋もれさせずに
        # 上位へ1件だけ繰り上げる。確信が高いものだけ試していると学習が進まない。
        speculative = next((o for o in ranked[self.top_n:] if o.score.speculative), None)
        if speculative and len(ranked) > self.top_n:
            ranked.remove(speculative)
            ranked.insert(min(self.top_n - 1, len(ranked)), speculative)
            logger.info("探索候補を繰り上げました: %s (opportunity=%s, confidence=%s)",
                        speculative.id, speculative.score.opportunity,
                        speculative.score.confidence)

        return_value = ranked
        report = render_daily_report(return_value, self.top_n, scanned=len(opportunities))

        if open_issue:
            self._open_issue(report, len(return_value))
        return return_value, report

    def _winner_count(self) -> int:
        """実際に収益が出た採用ニッチの数。explore 枠の比率を決めるのに使う。"""
        return len({r["niche_slug"] for r in self.ledger.rows("outcome")
                    if int(r.get("metrics", {}).get("revenue_jpy", 0)) > 0})

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
    def record_metrics(self, niche_slug: str, values: dict[str, int],
                       platform: str = "") -> str:
        """`/m` から実績を記録し、ファネル段階を診断して返す。

        入力を極限まで減らす方針（GPT提案⑨を採用）:
          - `posts` は自前のログから自動で埋める。人間に数えさせない
          - 必須は Core（views / revenue）だけ。1つも無くても Stage 0 で前に進む
          - 累計値で受け取り、前回からの差分はこちらで計算する
        """
        from .funnel import DEFAULT_PLATFORM, FunnelMetrics

        known = {n.slug for n in self.niches.load()}
        if niche_slug not in known:
            return (f"⚠️ `{niche_slug}` は採用済みニッチにありません。"
                    f"候補: {', '.join(sorted(known)) or '（なし）'}")

        posts = values.get("posts") or self._published_count(niche_slug)
        impressions = values.get("views", values.get("impressions"))

        metrics = FunnelMetrics(
            niche=niche_slug,
            platform=platform or values.get("platform") or DEFAULT_PLATFORM,
            posts=posts,
            impressions=impressions,
            revenue_jpy=values.get("revenue", 0),
            engaged=values.get("engaged"),
            cta_clicks=values.get("clicks", values.get("cta_clicks")),
            conversions=values.get("conversions", values.get("cv")),
            attention_minutes=self.ledger.attention_minutes(niche_slug),
            api_cost_jpy=values.get("cost", 0),
        )
        outcome = self.ledger.record_outcome(metrics)
        self.ledger.record_attention("metrics", niche_slug)
        verdict = self.ledger.diagnoser_for(metrics).diagnose(metrics)
        m = verdict.metrics

        lines = [
            f"📊 `{niche_slug}` の実績を記録しました"
            + (f"（投稿数は自動入力: {posts}本）。" if posts else "（投稿数は未取得）。"),
            "",
            f"**Stage {outcome.stage}: {outcome.stage_label}**",
            f"→ {verdict.prescription}",
            "",
            f"- {verdict.reason}",
        ]
        if outcome.delta:
            lines.append("- 前回からの増分: "
                         + " / ".join(f"{k} {v:+,}" for k, v in outcome.delta.items()))
        if posts:
            lines.append(f"- 1投稿あたりインプ: {m['impressions_per_post']:.0f}"
                         f"（下限 {m['distribution_floor']:.0f}）")

        optional = [("反応率", m["engagement_rate"], "{:.2%}"),
                    ("CTR", m["ctr"], "{:.2%}"),
                    ("CVR", m["cvr"], "{:.1%}"),
                    ("EPC", m["epc"], "{:.0f}円")]
        shown = [f"{name}: {fmt.format(v)}" for name, v, fmt in optional if v is not None]
        lines.append("- " + (" / ".join(shown) if shown else "反応系の指標は未入力（任意）"))
        lines.append(f"- RPM: {m['rpm']:.0f}円 / 1投稿あたり収益: {m['revenue_per_post']:.0f}円"
                     f" / 判断1分あたり: {m['revenue_per_attention_minute']:.0f}円")

        if verdict.should_exit:
            lines += ["", "🛑 **撤退を検討**: `/drop <opportunity_id>` で止められます。"]
        elif outcome.stage == 0:
            lines += ["", "次回は `/m " + niche_slug + " <累計views> <累計revenue>` を入れると"
                          "段階が診断できます。入れなくても運用は止まりません。"]
        return "\n".join(lines)

    @staticmethod
    def _published_count(niche_slug: str) -> int:
        """自前のログから公開本数を数える。人間に投稿数を入力させないため。"""
        try:
            from ..monetize.revenue import RevenueLog

            rows = RevenueLog()._read(RevenueLog().posts_csv)
            return sum(1 for r in rows
                       if r.get("category") == niche_slug and r.get("status") == "published")
        except Exception as exc:
            logger.debug("公開本数の自動集計をスキップしました: %s", exc)
            return 0

    def render_metrics_reminder(self, days: int = 7) -> str:
        """週次リマインダー本文。未更新の採用ニッチだけを、貼り付け可能な形で出す。"""
        stale = self.ledger.stale_niches(days)
        if not stale:
            return ""

        lines = ["実績が未更新の採用ニッチです。**数字を書き換えてコメントするだけ**でよく、"
                 "入力しなくても運用は止まりません（UNKNOWN として記録されます）。",
                 "",
                 "必要なのは累計の `views` と `revenue` の2つだけ。投稿数は自動で入ります。",
                 ""]
        for slug, ago in stale:
            when = f"{ago}日前" if ago >= 0 else "未入力"
            lines += [f"- `{slug}`（最終更新: {when}）", f"  `/m {slug} 0 0`"]
        lines += ["", "数字が1つしか分からないときは `/m <niche> <revenue>` でもよい。",
                  "完璧な台帳より、続く台帳を優先しています。"]
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
