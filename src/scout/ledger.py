"""Experiment Ledger — 予測と実績の突き合わせ台帳。

GPT の提案（採用）: 採用したテーマについて「なぜ採用したか / 何を期待したか /
実際どうだったか / どこで詰まったか」を残す。目的はログを増やすことではなく、
**探索側が自分の予測が当たったかを検証できるようにすること**。

実装上の要点2つ:
  1. 予測行は採用時に1度だけ書き、以後 **絶対に書き換えない**。あとから
     スコアを更新できてしまうと、予測の検証にならない
  2. 分析機構は今は作らない。予測と実績を貯めるだけにして、件数が閾値を超えたら
     相関を出す。1〜2週間に1採用のペースだと 20件でも数ヶ月かかるので、
     「先に正解を考えすぎない」（GPT提案⑥）を実行するには貯めるのが先

人間の判断時間（attention_minutes）も記録する。最終的な目的関数
「人間の判断1分あたりの期待収益」の分母は、推定ではなく実測できる唯一の項だから。
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR
from .funnel import FunnelDiagnoser, FunnelMetrics

logger = logging.getLogger(__name__)

LEDGER_DIR = DATA_DIR / "scout"

# 校正（配点の見直し）を始める最小件数。これ未満では相関を出さない。
CALIBRATION_MIN_ROWS = 20

# 1回の判断にかかる時間の既定値（秒）。実測が入るまでの仮の値。
ATTENTION_SECONDS = {"adopt": 90, "drop": 20, "approve": 40, "reject": 30, "metrics": 60}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Prediction:
    """採用時に凍結される予測。以後書き換えない。"""

    kind: str = "prediction"
    ts: str = ""
    opportunity_id: str = ""
    niche_slug: str = ""
    title: str = ""
    why_adopted: str = ""              # なぜ採用したか（判定理由）
    expected_action: str = ""           # 何をすると期待したか
    best_product: str = ""
    mapping_version: str = ""
    # 予測値。実績と1対1で突き合わせるための項目名にしてある。
    predicted_total: int = 0
    predicted_llm_total: int = 0
    predicted_discovery: float = 0.0
    predicted_business: float = 0.0
    predicted_opportunity: float = 0.0
    predicted_growth: int = 0
    predicted_low_competition: int = 0
    predicted_monetization: int = 0
    confidence: float = 0.0
    observed_ratio: float = 0.0
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Outcome:
    """実績。同じニッチに対して何度でも追記される（最新が有効）。"""

    kind: str = "outcome"
    ts: str = ""
    niche_slug: str = ""
    metrics: dict = field(default_factory=dict)
    stage: int = 0
    stage_label: str = ""
    decided: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AttentionEntry:
    """人間が判断に使った時間。目的関数の分母。"""

    kind: str = "attention"
    ts: str = ""
    action: str = ""
    niche_slug: str = ""
    seconds: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class ExperimentLedger:
    def __init__(self, directory: Path = LEDGER_DIR,
                 funnel_thresholds: dict | None = None):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "ledger.jsonl"
        self.diagnoser = FunnelDiagnoser(funnel_thresholds)

    # ------------------------------------------------------------------
    def _append(self, row: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def rows(self, kind: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind is None or row.get("kind") == kind:
                out.append(row)
        return out

    # ------------------------------------------------------------------
    def record_prediction(self, opportunity, niche_slug: str) -> Prediction:
        """採用時の予測を凍結する。同じ機会に対しては1回だけ書く。"""
        existing = {r.get("opportunity_id") for r in self.rows("prediction")}
        if opportunity.id in existing:
            logger.info("予測は既に記録済みです（上書きしません）: %s", opportunity.id)
            return next(Prediction(**r) for r in self.rows("prediction")
                        if r.get("opportunity_id") == opportunity.id)

        from .evidence import MAPPING_VERSION

        s = opportunity.score
        prediction = Prediction(
            ts=_now(), opportunity_id=opportunity.id, niche_slug=niche_slug,
            title=opportunity.candidate.title,
            why_adopted=s.rationale, expected_action=opportunity.action,
            best_product=opportunity.research.best_product,
            mapping_version=MAPPING_VERSION,
            predicted_total=s.total, predicted_llm_total=s.llm_total,
            predicted_discovery=s.discovery, predicted_business=s.business,
            predicted_opportunity=s.opportunity,
            predicted_growth=s.evidence.value("trend_growth"),
            predicted_low_competition=s.evidence.value("low_competition"),
            predicted_monetization=s.evidence.value("monetizability"),
            confidence=s.confidence, observed_ratio=s.observed_ratio,
            conflicts=list(s.conflicts),
        )
        self._append(prediction.to_dict())
        return prediction

    def record_outcome(self, metrics: FunnelMetrics, note: str = "") -> Outcome:
        """実績を追記し、ファネル段階を判定する。"""
        verdict = self.diagnoser.diagnose(metrics)
        outcome = Outcome(
            ts=_now(), niche_slug=metrics.niche, metrics=metrics.to_dict(),
            stage=verdict.stage, stage_label=verdict.label,
            decided=verdict.decided, note=note or verdict.prescription,
        )
        self._append(outcome.to_dict())
        return outcome

    def record_attention(self, action: str, niche_slug: str = "",
                         seconds: int | None = None) -> None:
        """判断1回分の時間を記録する。"""
        self._append(AttentionEntry(
            ts=_now(), action=action, niche_slug=niche_slug,
            seconds=seconds if seconds is not None else ATTENTION_SECONDS.get(action, 30),
        ).to_dict())

    # ------------------------------------------------------------------
    def latest_outcome(self, niche_slug: str) -> dict | None:
        rows = [r for r in self.rows("outcome") if r.get("niche_slug") == niche_slug]
        return rows[-1] if rows else None

    def attention_minutes(self, niche_slug: str | None = None) -> float:
        rows = self.rows("attention")
        if niche_slug:
            rows = [r for r in rows if r.get("niche_slug") == niche_slug]
        return round(sum(int(r.get("seconds", 0)) for r in rows) / 60, 1)

    def render_report(self) -> str:
        """台帳サマリ。週次レポートに載せる。"""
        predictions = self.rows("prediction")
        outcomes = self.rows("outcome")
        total_attention = self.attention_minutes()
        revenue = sum(int(r.get("metrics", {}).get("revenue_jpy", 0)) for r in outcomes)

        lines = [
            "## Experiment Ledger",
            "",
            f"- 採用したテーマ: **{len(predictions)}件**（校正開始まで残り "
            f"{max(0, CALIBRATION_MIN_ROWS - len(predictions))}件）",
            f"- 実績記録: {len(outcomes)}件",
            f"- 人間の判断時間: **{total_attention}分**",
        ]
        if total_attention:
            lines.append(f"- **判断1分あたり収益: {round(revenue / total_attention, 1)}円/分**"
                         "（これが最終的な目的関数の実測値）")

        stuck: dict[int, list[str]] = {}
        for row in outcomes:
            latest = self.latest_outcome(row["niche_slug"])
            if latest and latest.get("decided"):
                stuck.setdefault(latest["stage"], []).append(row["niche_slug"])
        if stuck:
            lines += ["", "### 詰まっている段階", ""]
            for stage in sorted(stuck):
                names = sorted(set(stuck[stage]))
                label = next((r["stage_label"] for r in outcomes if r["stage"] == stage), "")
                lines.append(f"- Stage {stage}（{label}）: {', '.join(names)}")

        lines += ["", self._calibration_line(predictions, outcomes)]
        return "\n".join(lines)

    def _calibration_line(self, predictions: list[dict], outcomes: list[dict]) -> str:
        """校正はデータが溜まるまで行わない（人間が先に正解を決めない）。"""
        if len(predictions) < CALIBRATION_MIN_ROWS:
            return (f"配点の校正は採用 {CALIBRATION_MIN_ROWS} 件以降に行う。"
                    f"それまでは 100点素点 / Discovery / Business を並列で貯めるだけにする。")

        pairs = self.prediction_outcome_pairs()
        if len(pairs) < CALIBRATION_MIN_ROWS:
            return f"予測と実績が対応した行が {len(pairs)}件。{CALIBRATION_MIN_ROWS}件で校正を開始する。"
        return (f"校正可能: {len(pairs)}件の予測/実績ペアが揃っている。"
                f"`python -m src.pipeline calibrate` で相関を確認する。")

    def prediction_outcome_pairs(self) -> list[tuple[dict, dict]]:
        """予測と最新実績の対応。校正分析の入力になる。"""
        pairs: list[tuple[dict, dict]] = []
        for p in self.rows("prediction"):
            outcome = self.latest_outcome(p.get("niche_slug", ""))
            if outcome:
                pairs.append((p, outcome))
        return pairs

    def calibration_table(self) -> list[dict]:
        """予測項目 vs 実績指標の対応表。相関を人間が読める形で出す。"""
        table: list[dict] = []
        for p, o in self.prediction_outcome_pairs():
            m = o.get("metrics", {})
            table.append({
                "niche": p.get("niche_slug", ""),
                "title": p.get("title", "")[:30],
                "predicted_opportunity": p.get("predicted_opportunity", 0),
                "predicted_total": p.get("predicted_total", 0),
                "predicted_low_competition": p.get("predicted_low_competition", 0),
                "actual_rpm": round(FunnelMetrics(**{
                    k: v for k, v in m.items()
                    if k in FunnelMetrics.__dataclass_fields__}).rpm, 1) if m else 0.0,
                "actual_revenue": m.get("revenue_jpy", 0),
                "actual_stage": o.get("stage", 0),
                "mapping_version": p.get("mapping_version", ""),
            })
        return table
