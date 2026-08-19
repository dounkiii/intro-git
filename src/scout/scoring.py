"""評価（ちゃっぴー案の GPT 担当分）。

ちゃっぴー案は「GPT に 100 点で採点させる」だったが、それだけでは占いになる。
LLM は「競合の少なさ」を検索せずに推測で答えられてしまうし、自信の度合いも
スコアに現れない。そこでこのモジュールは 2 段構えにしている。

  1. LLM に評価軸どおり採点させる（主観）
  2. 実測シグナルで補正する（客観）
     - 検索で見えた独立ドメイン数 vs LLM の「競合が少ない」判断 → 矛盾を検出
     - 根拠 URL が 0 件 → 信頼性を減点
     - いいね/時間が閾値未満 → 「伸び始めている」の否定
     - 何日も出続けているのに伸びていない → 継続性ではなく陳腐化として減点
     - 過去に実際に収益が出たカテゴリ → 加点（成果フィードバック）

順位付けは合計点ではなく `early_signal`（成長性 × 競合の少なさ）を主に見る。
合計点で並べると「すでに大流行しているテーマ」が上位に来て、システムの目的
（まだ供給が薄い市場を早く見つける）と逆になるため。
"""
from __future__ import annotations

import logging

from ..config import Config
from ..llm import ClaudeClient
from .models import RUBRIC, VERDICTS, Candidate, Opportunity, Research, Score

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは収益機会を採点する評価者です。

重要: 目的は「すでに大流行しているテーマ」を見つけることではなく、
「需要が生まれ始めているのに供給・競合が少ない市場」を早く見つけることです。
すでに大手が押さえているテーマは competition と demand が高くても低評価にしてください。

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


class Scorer:
    def __init__(self, config: Config, llm: ClaudeClient | None = None,
                 niche_revenue: dict[str, int] | None = None):
        self.config = config
        self.llm = llm or config.llm_client()
        scout = config.section("scout")
        thresholds = scout.get("thresholds", {}) or {}
        self.crowded_domains = int(thresholds.get("crowded_domains", 8))
        self.min_likes_per_hour = float(thresholds.get("min_likes_per_hour", 5))
        self.stale_after_seen = int(thresholds.get("stale_after_seen", 4))
        self.now_score = int(thresholds.get("now_score", 70))
        self.drop_score = int(thresholds.get("drop_score", 45))
        self.now_early_signal = float(thresholds.get("now_early_signal", 0.55))
        # 実際に収益が出たカテゴリへの加点（成果フィードバック）
        self.niche_revenue = niche_revenue or {}

    # ------------------------------------------------------------------
    def score(self, candidate: Candidate, research: Research,
              times_seen: int = 1) -> tuple[Score, str]:
        """(Score, action) を返す。LLM が使えない場合は実測のみのスコアになる。"""
        data = self._score_via_llm(candidate, research, times_seen)
        if data is None:
            score = Score(scored=False,
                          rationale="未採点（ANTHROPIC_API_KEY 未設定または生成失敗）")
            action = "手動で確認する（採点されていません）"
        else:
            score = Score(
                **{k: int(data.get(k, 0)) for k in RUBRIC},
                llm_verdict=data.get("verdict", "watch"),
                rationale=data.get("rationale", ""),
                scored=True,
            )
            action = data.get("action", "")

        self._apply_machine_adjustments(score, candidate, research, times_seen)
        return score, action

    def _score_via_llm(self, candidate: Candidate, research: Research,
                       times_seen: int) -> dict | None:
        if not self.llm.available:
            return None
        measured = research.measured or {}
        prompt = PROMPT_TEMPLATE.format(
            title=candidate.title,
            summary=candidate.summary or "(なし)",
            source=candidate.source,
            signals=candidate.signals or "(なし)",
            times_seen=times_seen,
            why_now=research.why_now or "不明",
            jp_demand=research.jp_demand or "不明",
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

    # ------------------------------------------------------------------
    def _apply_machine_adjustments(self, score: Score, candidate: Candidate,
                                   research: Research, times_seen: int) -> None:
        """実測シグナルでスコアを補正し、LLM との矛盾を記録する。"""
        measured = research.measured or {}
        domains = int(measured.get("competitor_domains", 0))
        evidence = int(measured.get("evidence_count", 0))

        # 1. 「競合が少ない」と言いながら、検索で大量のドメインが出ている
        if domains >= self.crowded_domains and score.low_competition >= 11:
            score.machine_adjust -= 10
            score.conflicts.append(
                f"LLMは競合が少ないと判断（{score.low_competition}/15）だが、"
                f"検索で独立ドメインが{domains}件見つかっている"
            )
            score.adjust_reasons.append(f"競合ドメイン{domains}件で -10")

        # 2. 根拠 URL が 1 件も無い
        if evidence == 0:
            score.machine_adjust -= 8
            score.adjust_reasons.append("根拠URLが0件で -8")
            if score.source_reliability >= 4:
                score.conflicts.append("根拠URLが0件なのに信頼性が高く採点されている")

        # 3. X 発掘なら伸びの速さを検証する（総いいね数ではなく速度）
        velocity = float(candidate.signals.get("likes_per_hour", 0) or 0)
        if candidate.source == "x_api":
            if velocity < self.min_likes_per_hour:
                score.machine_adjust -= 5
                score.adjust_reasons.append(
                    f"いいね/時間が{velocity}で閾値{self.min_likes_per_hour}未満のため -5")
            elif velocity >= self.min_likes_per_hour * 4:
                score.machine_adjust += 5
                score.adjust_reasons.append(f"いいね/時間が{velocity}で急伸のため +5")

        # 4. 何度も出てくるのに伸びない = 継続性ではなく陳腐化
        if times_seen >= self.stale_after_seen and velocity < self.min_likes_per_hour * 2:
            score.machine_adjust -= 5
            score.adjust_reasons.append(f"{times_seen}回観測されているが伸びていないため -5")

        # 5. 実際に収益が出たカテゴリなら加点（成果フィードバック）
        for keyword in candidate.keywords:
            revenue = self.niche_revenue.get(keyword, 0)
            if revenue > 0:
                score.machine_adjust += 5
                score.adjust_reasons.append(f"`{keyword}` は過去に{revenue:,}円の実績があり +5")
                break

    # ------------------------------------------------------------------
    def decide_verdict(self, score: Score) -> str:
        """最終判定。LLM と機械判定が食い違ったら保守的な側を採る。

        自動投稿まで繋がるので、判定は甘い側に倒さない。ただし採点自体が行われて
        いない場合（APIキー未設定など）は合計点0を「捨てる」と解釈せず保留する。
        """
        if not score.scored:
            return "watch"

        if score.total < self.drop_score:
            machine = "drop"
        elif score.total >= self.now_score and score.early_signal >= self.now_early_signal:
            machine = "now"
        else:
            machine = "watch"

        rank = {"drop": 0, "watch": 1, "now": 2}
        final = machine if rank[machine] <= rank.get(score.llm_verdict, 1) else score.llm_verdict
        if final != score.llm_verdict:
            score.conflicts.append(
                f"LLM判定は{score.llm_verdict}だが機械判定は{machine}。保守側の{final}を採用"
            )
        return final

    def rank(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        """順位付け。合計点ではなく early_signal を主軸にする。

        合計点だけで並べると「すでに大流行しているテーマ」が上に来てしまい、
        システムの目的と逆になる。
        """
        return sorted(
            opportunities,
            key=lambda o: (o.score.scored, o.score.early_signal, o.score.total,
                           float(o.candidate.signals.get("likes_per_hour", 0) or 0)),
            reverse=True,
        )
