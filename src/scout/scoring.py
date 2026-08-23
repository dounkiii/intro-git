"""評価。LLM の推測を、測れた分だけ実測で置き換える。

GPT との議論を経て変えた点:
  - 旧: LLM が 15点 → 実測と矛盾したら -10（推測と実測を足し引きしていた）
  - 新: 実測が取れた軸は **LLM 評価を置き換える**。矛盾は減点ではなくフラグとして残し、
        後で配点を校正するための教師データにする（src/scout/evidence.py）

  - 旧: 収益実績のあるキーワードに +5
  - 新: 削除。勝っている市場ばかり再発見するフィードバックループになるため、
        代わりに探索予算（explore/exploit）で制御する（src/scout/explore.py）

  - 旧: 順位は early_signal（成長性×競合の少なさ）
  - 新: 順位は opportunity = sqrt(discovery × business)。「入る余地」だけでなく
        「入って金になるか」も必要にした

実測できる軸（無料）:
  low_competition   ← SERP のドメイン種別分類（代理指標。confidence 低め）
  trend_growth      ← X のいいね/時間、観測回数に対する伸び
  source_reliability← 根拠URL数・独立ドメイン数
  production_fit    ← 自前の AFF_* で換金経路が組めるか（config と環境変数から実測）
"""
from __future__ import annotations

import logging
import math

from ..config import Config
from ..llm import ClaudeClient
from .models import (MONETIZATION_IMMEDIATE, MONETIZATION_NONE,
                     MONETIZATION_POTENTIAL, RUBRIC, VERDICTS, Candidate,
                     Opportunity, Research, Score)
from .serp import SerpAnalyzer, weakness_to_points

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは収益機会を採点する評価者です。

重要: 目的は「すでに大流行しているテーマ」を見つけることではなく、
「需要が生まれ始めているのに供給・競合が少ない市場」を早く見つけることです。
すでに大手が押さえているテーマは demand が高くても低評価にしてください。

採点は甘くしないでください。調査で「不明」だった項目は低く採点します。
根拠が確認できない主張には高い点を付けないでください。"""

PROMPT_TEMPLATE = """次のネタを評価軸どおりに採点してください。

## ネタ
タイトル: {title}
概要: {summary}
発掘元: {source}
機械計測シグナル: {signals}
これまでに観測された回数: {times_seen}回

## 調査結果
なぜ今なのか: {why_now}
日本市場の需要: {jp_demand}
海外の先行状況: {overseas_lead}
競合コンテンツの量: {competitor_note}
想定ユーザー: {target_user}
収益化方法: {monetization_paths}
最もおすすめ: {best_product}
リスク: {risks}
参照した独立ドメイン数（実測）: {competitor_domains}
根拠URL件数（実測）: {evidence_count}

## 評価軸（各項目の満点）
demand（需要）: 20
low_competition（競合の少なさ。競合が多いほど低い）: 15
monetizability（収益性）: 20
trend_growth（トレンド成長性）: 15
contentability（コンテンツ化しやすさ）: 10
affiliate_fit（アフィリエイトとの相性）: 10
durability（継続性。一過性なら低い）: 5
source_reliability（情報の信頼性）: 5

## 判定
verdict は now（今すぐ狙う） / watch（様子見） / drop（捨てる）のいずれか。
rationale は 2 文以内で、なぜその点数なのかを書く。
action は「今日これをやる」という具体的な 1 アクションを 1 文で書く。"""

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": "integer", "minimum": 0, "maximum": v} for k, v in RUBRIC.items()},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "rationale": {"type": "string"},
        "action": {"type": "string"},
    },
    "required": [*RUBRIC.keys(), "verdict", "rationale", "action"],
    "additionalProperties": False,
}

# 推測と実測がこれ以上ズレたら矛盾として記録する（配点校正の教師データ）
DIVERGENCE_THRESHOLD = 5


class Scorer:
    def __init__(self, config: Config, llm: ClaudeClient | None = None):
        self.config = config
        self.llm = llm or config.llm_client()
        scout = config.section("scout")
        t = scout.get("thresholds", {}) or {}
        self.min_likes_per_hour = float(t.get("min_likes_per_hour", 5))
        self.stale_after_seen = int(t.get("stale_after_seen", 4))
        self.now_score = int(t.get("now_score", 70))
        self.drop_score = int(t.get("drop_score", 45))
        self.now_opportunity = float(t.get("now_opportunity", 30))
        self.drop_opportunity = float(t.get("drop_opportunity", 10))
        # confidence はスコアに掛けないが、`now`（本気で投資する）判定のゲートに使う。
        # 低確信のものは watch に留め、explore 枠で意図的に試す対象にする。
        self.now_confidence = float(t.get("now_confidence", 0.45))
        self.serp = SerpAnalyzer(provider=scout.get("serp_provider", "heuristic"))
        self._affiliate = None

    # ------------------------------------------------------------------
    def score(self, candidate: Candidate, research: Research,
              times_seen: int = 1) -> tuple[Score, str]:
        data = self._score_via_llm(candidate, research, times_seen)
        if data is None:
            score = Score(scored=False,
                          rationale="未採点（LLM の API キー未設定、または生成失敗）")
            action = "手動で確認する（採点されていません）"
        else:
            score = Score(
                **{k: int(data.get(k, 0)) for k in RUBRIC},
                llm_verdict=data.get("verdict", "watch"),
                rationale=data.get("rationale", ""),
                scored=True,
            )
            action = data.get("action", "")

        self._observe(score, candidate, research, times_seen)
        self._record_divergences(score)
        return score, action

    def _score_via_llm(self, candidate: Candidate, research: Research,
                       times_seen: int) -> dict | None:
        if not self.llm.available:
            return None
        measured = research.measured or {}
        prompt = PROMPT_TEMPLATE.format(
            title=candidate.title, summary=candidate.summary or "(なし)",
            source=candidate.source, signals=candidate.signals or "(なし)",
            times_seen=times_seen,
            why_now=research.why_now or "不明", jp_demand=research.jp_demand or "不明",
            overseas_lead=research.overseas_lead or "不明",
            competitor_note=research.competitor_note or "不明",
            target_user=research.target_user or "不明",
            monetization_paths=", ".join(research.monetization_paths) or "不明",
            best_product=research.best_product or "不明",
            risks=", ".join(research.risks) or "不明",
            competitor_domains=measured.get("competitor_domains", 0),
            evidence_count=measured.get("evidence_count", 0),
        )
        return self.llm.generate_json(SYSTEM_PROMPT, prompt, SCORE_SCHEMA)

    # --- 実測による置き換え ---------------------------------------------
    def _observe(self, score: Score, candidate: Candidate, research: Research,
                 times_seen: int) -> None:
        self._observe_competition(score, research)
        self._observe_growth(score, candidate, times_seen)
        self._observe_reliability(score, research)
        score.monetization_observed = self._has_affiliate_route(candidate)
        score.monetization_inferred = self._has_inferred_potential(research)

    def _observe_competition(self, score: Score, research: Research) -> None:
        """SERP の守備力から「競合の少なさ」を実測で置き換える。"""
        results = research.measured.get("results") or []
        if not results:
            return
        weak = self.serp.analyze(results, research.measured.get("keywords", []))
        if weak.confidence <= 0.15:
            score.notes.append(f"SERP判定を採用せず（{'; '.join(weak.notes)}）")
            return

        points = weakness_to_points(weak.weakness, RUBRIC["low_competition"])
        score.evidence.observe(
            "low_competition", RUBRIC["low_competition"], points,
            source=f"serp_{weak.provider}", confidence=weak.confidence,
            note=f"weakness={weak.weakness} 内訳={weak.breakdown} "
                 f"意図一致率={weak.intent_match_ratio} 古さ={weak.stale_ratio}",
        )
        research.measured["serp"] = weak.to_dict()

    def _observe_growth(self, score: Score, candidate: Candidate,
                        times_seen: int) -> None:
        """X のいいね/時間から「成長性」を実測で置き換える。"""
        velocity = float(candidate.signals.get("likes_per_hour", 0) or 0)
        if candidate.source != "x_api" or velocity <= 0:
            return

        # 対数換算。GPT からの指摘（採用）: SNS 指標の分布は 10/20/40/…/10000 のように
        # 極端に歪むので線形（閾値の4倍で満点）は上位を潰し下位を過大評価する。
        # 最終的には同一プラットフォーム・カテゴリ内の percentile にしたいが、
        # 分布が取れるまでは log で近似する（TODO: 実績30件で percentile に切替）。
        ceiling = self.min_likes_per_hour * 20      # この付近で満点に漸近
        ratio = min(1.0, math.log1p(velocity) / math.log1p(ceiling)) if ceiling > 0 else 0.0
        points = round(ratio * RUBRIC["trend_growth"])
        note = f"likes_per_hour={velocity} (log換算)"

        # 何度も観測されているのに伸びない = 継続性ではなく陳腐化
        if times_seen >= self.stale_after_seen and velocity < self.min_likes_per_hour * 2:
            points = max(0, points - 5)
            note += f" / {times_seen}回観測されているが伸びていない"

        score.evidence.observe("trend_growth", RUBRIC["trend_growth"], points,
                               source="x_velocity", confidence=0.7, note=note)

    def _observe_reliability(self, score: Score, research: Research) -> None:
        """根拠の量から「情報の信頼性」を実測で置き換える。"""
        measured = research.measured or {}
        evidence_count = int(measured.get("evidence_count", 0))
        domains = int(measured.get("competitor_domains", 0))
        if evidence_count == 0 and domains == 0 and not research.sources:
            score.evidence.observe("source_reliability", RUBRIC["source_reliability"], 0,
                                   source="evidence_count", confidence=0.9,
                                   note="根拠URLが0件")
            return
        # 独立ドメイン3件以上で満点。1件のみは片寄りとみなす。
        points = min(RUBRIC["source_reliability"], round(domains / 3 * RUBRIC["source_reliability"]))
        score.evidence.observe("source_reliability", RUBRIC["source_reliability"], points,
                               source="evidence_count", confidence=0.8,
                               note=f"独立ドメイン{domains}件 / 根拠URL{evidence_count}件")

    # 換金の道がありそうかを示す語。調査結果から potential を判定するのに使う。
    POTENTIAL_HINTS = ("有料", "販売", "商品", "サービス", "SaaS", "ツール", "講座",
                       "テンプレート", "リード", "見積", "相談", "比較", "note", "案件")

    def _has_affiliate_route(self, candidate: Candidate) -> bool:
        """**実測**: 自前の AFF_* に案件が実在するか。

        `observed` 側。ここだけが「実際に案件が存在した」という事実。
        """
        if self._affiliate is None:
            from ..monetize.affiliate import AffiliateEngine

            self._affiliate = AffiliateEngine(self.config)

        # quiet=True: 経路の有無を調べるだけなので、キーワードごとに警告を出さない
        return any(self._affiliate.build(key, quiet=True).has_route
                   for key in [*candidate.keywords, "default"])

    def _has_inferred_potential(self, research: Research) -> bool:
        """**推論**: 案件が無くても収益化の道があると LLM が言っているか。

        `inferred` 側。observed とは別のフィールドに保存し、Ledger でも
        `monetization_source` として区別する。校正時に「LLM が稼げると言った」と
        「実際に案件が存在した」を同じ種類のデータとして扱わないため。
        """
        text = " ".join([*research.monetization_paths, research.best_product])
        return bool(research.monetization_paths
                    or any(h in text for h in self.POTENTIAL_HINTS))

    def _record_divergences(self, score: Score) -> None:
        """推測と実測のズレを矛盾として記録する（減点はしない）。"""
        for axis, diff in score.evidence.divergences().items():
            if abs(diff) < DIVERGENCE_THRESHOLD:
                continue
            ev = score.evidence.items[axis]
            direction = "過大評価" if diff < 0 else "過小評価"
            score.conflicts.append(
                f"{axis}: LLM {ev.inferred} → 実測 {ev.observed}（{direction} {abs(diff)}点, "
                f"source={ev.source}, confidence={ev.confidence}）"
            )

    # ------------------------------------------------------------------
    def decide_verdict(self, score: Score) -> str:
        """LLM 判定 / 素点 / opportunity の3つで、最も保守的なものを採る。"""
        if not score.scored:
            return "watch"

        if score.total < self.drop_score or score.opportunity < self.drop_opportunity:
            machine = "drop"
        elif score.total >= self.now_score and score.opportunity >= self.now_opportunity:
            # confidence は順位には効かせないが、`now`（本気で投資する）には要求する。
            # 高スコア・低確信は捨てずに watch へ置き、explore 枠で試す。
            if score.confidence >= self.now_confidence:
                machine = "now"
            else:
                machine = "watch"
                score.notes.append(
                    f"スコアは now 相当だが根拠が薄い（confidence {score.confidence} "
                    f"< {self.now_confidence}）ため watch。explore 枠での検証向き")
        else:
            machine = "watch"

        rank = {"drop": 0, "watch": 1, "now": 2}
        final = machine if rank[machine] <= rank.get(score.llm_verdict, 1) else score.llm_verdict
        if final != score.llm_verdict:
            score.conflicts.append(
                f"LLM判定は{score.llm_verdict}だが機械判定は{machine}"
                f"（総合{score.total} / 機会{score.opportunity}）。保守側の{final}を採用"
            )
        return final

    def rank(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        """順位付け。opportunity = sqrt(discovery × business) を主軸にする。

        discovery だけで並べると「入る余地はあるが金にならない」テーマが上位に来る。
        business だけで並べると「金になるが大手だらけ」のテーマが上位に来る。
        相乗平均なので、どちらかがゼロに 近い候補は上に来ない。

        confidence は順位に入れない（早いトレンドほど根拠が薄く、掛けると
        成熟したネタを好むシステムになるため）。不確実性は別に表示する。
        """
        return sorted(
            opportunities,
            key=lambda o: (o.score.scored, o.score.opportunity, o.score.discovery,
                           float(o.candidate.signals.get("likes_per_hour", 0) or 0)),
            reverse=True,
        )
