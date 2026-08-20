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

# 運用上の異常検知を行う間隔。統計的校正とは別で、配点は一切変更しない。
DIAGNOSTIC_REVIEW_EVERY = 5

# 同じ異常がこの回数連続したら、20件を待たずに点検する（再開条件その3）。
# ただし点検の対象は実装バグ・運用障害に限り、アルゴリズムは触らない。
REPEAT_ESCALATION = 2

# 20件未満でも直してよいもの（実装バグ・運用障害）
FIXABLE_BEFORE_CALIBRATION = (
    "publish_zero", "publish_low", "metrics_missing", "transition_stuck",
)
# 20件未満では原則触らないもの（アルゴリズム）
FROZEN_UNTIL_CALIBRATION = (
    "cause_concentrated", "speculative_shutout", "stage1_dominant",
    "diagnosing_concentrated",
)

ANOMALY_LABELS = {
    "publish_zero": "採用しても1本も公開されていない",
    "publish_low": "公開到達率が低い",
    "metrics_missing": "views 未入力が多く Stage 判定ができない",
    "transition_stuck": "投資レベルが動いていない",
    "cause_concentrated": "推定原因が1つに集中している",
    "speculative_shutout": "探索候補が全滅している",
    "stage1_dominant": "Stage 1（配信の失敗）に偏っている",
    "diagnosing_concentrated": "診断中の原因が1つに集中している",
}

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
    speculative_rule_version: str = ""
    commitment: str = ""
    speculative: bool = False
    # 予測値。実績と1対1で突き合わせるための項目名にしてある。
    predicted_total: int = 0
    predicted_llm_total: int = 0
    predicted_discovery: float = 0.0
    predicted_business: float = 0.0
    predicted_opportunity: float = 0.0
    predicted_growth: int = 0
    predicted_low_competition: int = 0
    predicted_monetization: int = 0
    # 換金の根拠が実測か推論か。校正時に混ぜないための区別。
    monetization_readiness: str = ""
    monetization_source: str = ""
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
    platform: str = ""
    metrics: dict = field(default_factory=dict)
    delta: dict = field(default_factory=dict)   # 前回からの増分（入力は累計値で受ける）
    stage: int = 0
    stage_label: str = ""
    likely_cause: str = "unknown"
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
        self.funnel_thresholds = funnel_thresholds
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
    def record_prediction(self, opportunity, niche_slug: str,
                          commitment: str = "") -> Prediction:
        """採用時の予測を凍結する。同じ機会に対しては1回だけ書く。"""
        existing = {r.get("opportunity_id") for r in self.rows("prediction")}
        if opportunity.id in existing:
            logger.info("予測は既に記録済みです（上書きしません）: %s", opportunity.id)
            return next(Prediction(**r) for r in self.rows("prediction")
                        if r.get("opportunity_id") == opportunity.id)

        from .evidence import MAPPING_VERSION
        from .models import SPECULATIVE_RULE_VERSION

        s = opportunity.score
        prediction = Prediction(
            ts=_now(), opportunity_id=opportunity.id, niche_slug=niche_slug,
            title=opportunity.candidate.title,
            why_adopted=s.rationale, expected_action=opportunity.action,
            best_product=opportunity.research.best_product,
            mapping_version=MAPPING_VERSION,
            speculative_rule_version=SPECULATIVE_RULE_VERSION,
            commitment=commitment, speculative=s.speculative,
            predicted_total=s.total, predicted_llm_total=s.llm_total,
            predicted_discovery=s.discovery, predicted_business=s.business,
            predicted_opportunity=s.opportunity,
            predicted_growth=s.evidence.value("trend_growth"),
            predicted_low_competition=s.evidence.value("low_competition"),
            predicted_monetization=s.evidence.value("monetizability"),
            monetization_readiness=s.monetization_readiness,
            monetization_source=s.monetization_source,
            confidence=s.confidence, observed_ratio=s.observed_ratio,
            conflicts=list(s.conflicts),
        )
        self._append(prediction.to_dict())
        return prediction

    def record_outcome(self, metrics: FunnelMetrics, note: str = "",
                       creatives_tried: int = 1) -> Outcome:
        """実績を追記し、ファネル段階を判定する。

        入力は累計値で受け取り、前回との差分をこちらで計算する（人間に引き算をさせない）。
        """
        verdict = self.diagnoser_for(metrics).diagnose(metrics, creatives_tried)
        outcome = Outcome(
            ts=_now(), niche_slug=metrics.niche, platform=metrics.platform,
            metrics=metrics.to_dict(), delta=self._delta(metrics),
            stage=verdict.stage, stage_label=verdict.label,
            likely_cause=verdict.likely_cause,
            decided=verdict.decided, note=note or verdict.prescription,
        )
        self._append(outcome.to_dict())
        return outcome

    def diagnoser_for(self, metrics: FunnelMetrics) -> FunnelDiagnoser:
        """プラットフォームと自アカウントの実績分布に合わせた判定器を返す。"""
        return FunnelDiagnoser(
            self.funnel_thresholds, platform=metrics.platform,
            baseline_samples=self.baseline_samples(metrics.platform),
            peer_samples=self.peer_samples(metrics.platform),
        )

    def revenue_events(self, niche_slug: str) -> int:
        """売上が増えたことを観測した回数。

        「売れた」と「再現性がある」を分けるために使う。1件の売上は偶然の可能性が
        あるので、これが 2 以上になるまで SCALE には上げない。
        """
        seen = 0
        previous = 0
        for row in sorted((r for r in self.rows("outcome")
                           if r.get("niche_slug") == niche_slug),
                          key=lambda r: r.get("ts", "")):
            revenue = int(row.get("metrics", {}).get("revenue_jpy", 0))
            if revenue > previous:
                seen += 1
            previous = max(previous, revenue)
        return seen

    def peer_samples(self, platform: str = "") -> dict[str, float]:
        """{niche_slug: 最新の1投稿あたりインプ}。同フォーマットの他ニッチとの比較用。

        「Aニッチは3000でBニッチは200」という比較ができて初めて、ニッチ側が
        原因だと言える（Stage 1 を原因の断定に使わないため）。
        """
        latest: dict[str, float] = {}
        for row in self.rows("outcome"):
            if platform and row.get("platform") and row["platform"] != platform:
                continue
            slug = row.get("niche_slug", "")
            per_post = row.get("metrics", {}).get("impressions_per_post")
            if per_post is None:
                m = row.get("metrics", {})
                posts, impressions = m.get("posts") or 0, m.get("impressions")
                per_post = (impressions / posts) if posts and impressions else 0
            if slug and per_post:
                latest[slug] = float(per_post)
        return latest

    def baseline_samples(self, platform: str = "") -> list[float]:
        """自アカウントの「1投稿あたりインプ」の実績列。判定の基準に使う。"""
        samples: list[float] = []
        for row in self.rows("outcome"):
            if platform and row.get("platform") and row["platform"] != platform:
                continue
            per_post = row.get("metrics", {}).get("impressions_per_post")
            if per_post is None:
                m = row.get("metrics", {})
                posts, impressions = m.get("posts") or 0, m.get("impressions")
                per_post = (impressions / posts) if posts and impressions else 0
            if per_post:
                samples.append(float(per_post))
        return samples

    def _delta(self, metrics: FunnelMetrics) -> dict:
        previous = self.latest_outcome(metrics.niche)
        if not previous:
            return {}
        before = previous.get("metrics", {})
        delta: dict[str, int] = {}
        for key in ("posts", "impressions", "revenue_jpy", "cta_clicks", "conversions"):
            now_v, before_v = getattr(metrics, key, None), before.get(key)
            if now_v is None or before_v is None:
                continue
            delta[key] = int(now_v) - int(before_v)
        return delta

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

    # --- 最重要KPI ---------------------------------------------------
    def adoptions_to_first_revenue(self) -> tuple[int | None, int]:
        """(初売上までに要した採用件数, 現在の採用件数)。

        GPT の提案（採用）: このプロジェクトで当面追う数字を1つ選ぶならこれ。
        3件で初売上なら探索が効いている。40件で0円なら探索・production_fit・
        案件選定のどこかが根本的に間違っている。
        """
        predictions = sorted(self.rows("prediction"), key=lambda r: r.get("ts", ""))
        earning = {r["niche_slug"] for r in self.rows("outcome")
                   if int(r.get("metrics", {}).get("revenue_jpy", 0)) > 0}
        for i, p in enumerate(predictions, start=1):
            if p.get("niche_slug") in earning:
                return i, len(predictions)
        return None, len(predictions)

    def publish_rate(self) -> tuple[int, int]:
        """(1本以上公開できた採用ニッチ数, 採用ニッチ数)。

        初売上までの採用件数は一度しか観測できない遅行指標なので、毎週見られる
        先行指標としてこれを並べる。採用しても公開に至っていなければ、
        下流のスコア精度をいくら上げても意味がない。
        """
        adopted = {r["niche_slug"] for r in self.rows("prediction")}
        published = {r["niche_slug"] for r in self.rows("outcome")
                     if int(r.get("metrics", {}).get("posts", 0)) > 0}
        return len(adopted & published), len(adopted)

    def published_items_to_first_revenue(self) -> tuple[int | None, int]:
        """(初売上までに市場へ出した本数, 現在の累計公開本数)。

        「初売上までの採用件数」だけだと「1採用で100円」が極端に高評価される。
        公開本数で見ると「何本出したら売上シグナルが出たか」が分かる。
        """
        rows = sorted(self.rows("outcome"), key=lambda r: r.get("ts", ""))
        cumulative: dict[str, int] = {}
        for row in rows:
            slug = row.get("niche_slug", "")
            posts = int(row.get("metrics", {}).get("posts", 0))
            cumulative[slug] = max(cumulative.get(slug, 0), posts)
            if int(row.get("metrics", {}).get("revenue_jpy", 0)) > 0:
                return sum(cumulative.values()), sum(cumulative.values())
        return None, sum(cumulative.values())

    def revenue_per_published_item(self) -> float:
        """公開1本あたり収益。Economics 層の指標。"""
        best: dict[str, tuple[int, int]] = {}
        for row in self.rows("outcome"):
            slug = row.get("niche_slug", "")
            m = row.get("metrics", {})
            posts, revenue = int(m.get("posts", 0)), int(m.get("revenue_jpy", 0))
            prev = best.get(slug, (0, 0))
            best[slug] = (max(prev[0], posts), max(prev[1], revenue))
        posts_total = sum(p for p, _ in best.values())
        revenue_total = sum(r for _, r in best.values())
        return round(revenue_total / posts_total, 1) if posts_total else 0.0

    def detect_anomalies(self) -> dict[str, str]:
        """運用上の異常を検出する。{異常コード: 詳細} を返す。

        コードで返すのは、前回のレビュー結果と突き合わせて
        「同じ異常が2回連続したか」を判定するため。
        """
        predictions = self.rows("prediction")
        outcomes = self.rows("outcome")
        anomalies: dict[str, str] = {}

        published, adopted = self.publish_rate()
        if adopted and published == 0:
            anomalies["publish_zero"] = f"{adopted}件採用して公開0本"
        elif adopted and published < adopted / 2:
            anomalies["publish_low"] = f"公開到達率 {published}/{adopted}"

        stages: dict[int, int] = {}
        causes: dict[str, int] = {}
        for slug in {r["niche_slug"] for r in outcomes}:
            latest = self.latest_outcome(slug)
            if not latest:
                continue
            stages[latest["stage"]] = stages.get(latest["stage"], 0) + 1
            cause = latest.get("likely_cause", "unknown")
            causes[cause] = causes.get(cause, 0) + 1

        decided = sum(v for k, v in stages.items() if k != 0)
        if decided >= 3 and stages.get(1, 0) >= decided * 0.6:
            anomalies["stage1_dominant"] = f"Stage1 が {stages[1]}/{decided}件"

        judged = {k: v for k, v in causes.items() if k != "unknown"}
        if judged:
            code, count = max(judged.items(), key=lambda kv: kv[1])
            if count >= 3:
                anomalies["cause_concentrated"] = f"`{code}` に {count}件"
                if code == "offer":
                    anomalies["diagnosing_concentrated"] = f"案件・商品の問題が {count}件"

        spec = [r for r in predictions if r.get("speculative")]
        if len(spec) >= 3:
            earning = {r["niche_slug"] for r in outcomes
                       if int(r.get("metrics", {}).get("revenue_jpy", 0)) > 0}
            if not any(r.get("niche_slug") in earning for r in spec):
                anomalies["speculative_shutout"] = f"探索候補 {len(spec)}件すべて収益0"

        if outcomes:
            missing = sum(1 for r in outcomes
                          if r.get("metrics", {}).get("impressions") is None)
            if missing / len(outcomes) > 0.5:
                anomalies["metrics_missing"] = f"views 未入力 {missing}/{len(outcomes)}件"

        # 投資レベルが一度も動いていない = 状態遷移が壊れている可能性
        if len(outcomes) >= 3 and predictions:
            levels = {r.get("commitment", "") for r in predictions}
            moved = any(o.get("stage", 0) not in (0,) for o in outcomes)
            if moved and len(levels) <= 1 and not self._level_changed():
                anomalies["transition_stuck"] = "実績が入っているのにレベルが未変化"

        return anomalies

    def _level_changed(self) -> bool:
        """ニッチの投資レベルが初期値から動いたことがあるか。"""
        try:
            from .niches import NicheRegistry

            return any(n.level_reason and "レベル変更なし" not in n.level_reason
                       for n in NicheRegistry().load())
        except Exception:
            return True     # 判定できないときは異常扱いにしない

    def repeated_anomalies(self, current: dict[str, str]) -> dict[str, int]:
        """今回の異常のうち、過去のレビューから連続しているものと連続回数。"""
        history = [set(r.get("anomalies", {})) for r in self.rows("review")]
        repeated: dict[str, int] = {}
        for code in current:
            streak = 1
            for past in reversed(history):
                if code in past:
                    streak += 1
                else:
                    break
            if streak >= REPEAT_ESCALATION:
                repeated[code] = streak
        return repeated

    def diagnostic_review(self, force: bool = False) -> list[str]:
        """5件ごとの運用上の異常検知。**配点・mapping・ランキング式は変更しない。**

        統計的校正（20件以降）とは別物。N=5 でも「5採用して公開0本」は明らかに問題で、
        それは配点の話ではなく運用の話だから。

        同じ異常が2回連続したら、20件を待たずに点検対象として明示する。
        ただし点検の対象は**実装バグ・運用障害に限り、アルゴリズムは触らない**。
        """
        predictions = self.rows("prediction")
        n = len(predictions)
        if not force and (n == 0 or n % DIAGNOSTIC_REVIEW_EVERY != 0):
            return []

        anomalies = self.detect_anomalies()
        repeated = self.repeated_anomalies(anomalies)
        self._append({"kind": "review", "ts": _now(), "adopted": n,
                      "anomalies": anomalies, "repeated": repeated})

        lines = [f"### 診断レビュー（採用 {n} 件時点・配点は変更しない）", ""]
        if not anomalies:
            lines.append("- 運用上の異常は検出されていません。")
            lines += ["", f"配点・mapping・ランキング式の変更は採用 "
                          f"{CALIBRATION_MIN_ROWS} 件以降に検討する。"]
            return lines

        fixable = {k: v for k, v in anomalies.items() if k in FIXABLE_BEFORE_CALIBRATION}
        frozen = {k: v for k, v in anomalies.items() if k in FROZEN_UNTIL_CALIBRATION}

        if fixable:
            lines += ["**今すぐ直してよい（実装バグ・運用障害）**", ""]
            for code, detail in fixable.items():
                mark = f"🚨 {repeated[code]}回連続 " if code in repeated else "⚠️ "
                lines.append(f"- {mark}{ANOMALY_LABELS.get(code, code)}: {detail}")
            lines.append("")

        if frozen:
            lines += ["**記録のみ（アルゴリズムは20件まで触らない）**", ""]
            for code, detail in frozen.items():
                mark = f"🚨 {repeated[code]}回連続 " if code in repeated else "・"
                lines.append(f"- {mark}{ANOMALY_LABELS.get(code, code)}: {detail}")
            lines.append("")

        if repeated:
            lines += [
                f"🚨 **同じ異常が{REPEAT_ESCALATION}回以上連続しています。"
                f"20件を待たずに点検してください。**",
                "",
                "点検してよいのは実装バグ・運用障害だけです"
                "（公開されない / metrics が取れない / 状態遷移がおかしい / "
                "人間の明示指示が無視される）。",
                "配点・mapping・scale_gate・speculative閾値・opportunity計算式・"
                "monetization の重みは触りません。",
                "",
            ]

        lines.append(f"配点・mapping・ランキング式の変更は採用 "
                     f"{CALIBRATION_MIN_ROWS} 件以降に検討する。")
        return lines

    def first_revenue_postmortem(self) -> list[str]:
        """初売上が出たときの振り返り。**配点を変える前に事実を記録する。**

        初売上が出てもすぐ配点を変えない。まず「何が売れたか / どの Stage を通ったか /
        speculative か通常候補か / CHEAP_TEST からどう遷移したか / 何本で到達したか」を
        記録し、再現性を見る。
        """
        outcomes = sorted(self.rows("outcome"), key=lambda r: r.get("ts", ""))
        winner = next((r for r in outcomes
                       if int(r.get("metrics", {}).get("revenue_jpy", 0)) > 0), None)
        if winner is None:
            return []

        slug = winner.get("niche_slug", "")
        prediction = next((r for r in self.rows("prediction")
                           if r.get("niche_slug") == slug), {})
        path = [f"Stage{r.get('stage')}" for r in outcomes
                if r.get("niche_slug") == slug]
        first_items, _ = self.published_items_to_first_revenue()
        adoptions, _ = self.adoptions_to_first_revenue()

        return [
            "### 🎉 初売上の振り返り（配点はまだ変えない）",
            "",
            f"- **何が売れたか**: {prediction.get('title', slug)}（`{slug}`）",
            f"- **最初に作ったもの**: {prediction.get('best_product') or '（未記録）'}",
            f"- **通った Stage**: {' → '.join(path) or '（未記録）'}",
            f"- **候補の種類**: "
            + ("探索候補（speculative）" if prediction.get("speculative") else "通常候補"),
            f"- **採用時の投資レベル**: {prediction.get('commitment') or '（未記録）'}",
            f"- **換金の根拠**: {prediction.get('monetization_source') or '（未記録）'}"
            f"（{prediction.get('monetization_readiness') or '不明'}）",
            f"- **採用時の予測**: 機会 {prediction.get('predicted_opportunity', 0)} / "
            f"確信 {prediction.get('confidence', 0)}",
            f"- **到達までの採用件数**: {adoptions}件 / **公開本数**: {first_items}本",
            "",
            "次にやるのは配点変更ではなく **再現性の確認**。"
            f"`{slug}` と同じ構成（Stage 遷移・候補の種類・換金の根拠）で"
            "もう1件出せるかを見る。",
        ]

    def stale_niches(self, days: int = 7) -> list[tuple[str, int]]:
        """実績が更新されていない採用ニッチ。週次リマインダー Issue に使う。

        戻り値は (niche_slug, 最終更新からの日数)。未更新は日数 -1。
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        latest: dict[str, datetime] = {}
        for row in self.rows("outcome"):
            ts = self._parse_ts(row.get("ts", ""))
            slug = row.get("niche_slug", "")
            if ts and (slug not in latest or ts > latest[slug]):
                latest[slug] = ts

        stale: list[tuple[str, int]] = []
        for row in self.rows("prediction"):
            slug = row.get("niche_slug", "")
            if not slug:
                continue
            seen = latest.get(slug)
            if seen is None:
                stale.append((slug, -1))
            elif seen < cutoff:
                stale.append((slug, (datetime.now(timezone.utc) - seen).days))
        return sorted(set(stale), key=lambda x: -x[1])

    @staticmethod
    def _parse_ts(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def render_report(self) -> str:
        """台帳サマリ。週次レポートに載せる。"""
        predictions = self.rows("prediction")
        outcomes = self.rows("outcome")
        total_attention = self.attention_minutes()
        revenue = sum(int(r.get("metrics", {}).get("revenue_jpy", 0)) for r in outcomes)

        first, adopted = self.adoptions_to_first_revenue()
        published, adopted_total = self.publish_rate()
        items_to_revenue, items_total = self.published_items_to_first_revenue()

        lines = ["## Experiment Ledger", "", "### North Star", ""]
        if first is not None:
            lines.append(f"- 🎉 **初売上までの採用件数: {first}件**（探索が効いている）")
        else:
            lines.append(f"- **初売上までの採用件数: 未達（現在 {adopted}件）**"
                         + ("　⚠️ 20件を超えても0円なら探索・換金経路・案件選定のどこかが"
                            "根本的に間違っている" if adopted >= 20 else ""))

        # 3層に分けるのは、North Star 単独だと「1採用で100円」が過大評価されるため。
        rate = f"{published}/{adopted_total}" if adopted_total else "0/0"
        lines += [
            "",
            "### 診断用の3層",
            "",
            f"1. **Execution** 公開到達率: **{rate}**"
            + ("　⚠️ 採用しても市場に出ていない。下流のスコア精度より先にここ"
               if adopted_total and published < adopted_total / 2 else ""),
            f"2. **Speed to Signal** 初売上までの公開本数: "
            + (f"**{items_to_revenue}本**" if items_to_revenue is not None
               else f"未達（累計 {items_total}本）"),
            f"3. **Economics** 公開1本あたり収益: **{self.revenue_per_published_item():.0f}円**"
            + (f" / 1,000viewsあたり {self._overall_rpm():.0f}円"
               if self._overall_rpm() else ""),
        ]

        lines += [
            "",
            "### 台帳",
            "",
            f"- 採用したテーマ: **{len(predictions)}件**（校正開始まで残り "
            f"{max(0, CALIBRATION_MIN_ROWS - len(predictions))}件）",
            f"- 実績記録: {len(outcomes)}件",
            f"- 人間の判断時間: **{total_attention}分**",
        ]
        if total_attention:
            lines.append(f"- **判断1分あたり収益: {round(revenue / total_attention, 1)}円/分**"
                         "（これが最終的な目的関数の実測値）")

        stale = self.stale_niches()
        if stale:
            names = ", ".join(f"`{s}`" + (f"（{d}日前）" if d >= 0 else "（未入力）")
                              for s, d in stale[:8])
            lines.append(f"- 実績が未更新: {names}")

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

        postmortem = self.first_revenue_postmortem()
        if postmortem:
            lines += ["", *postmortem]

        review = self.diagnostic_review()
        if review:
            lines += ["", *review]

        lines += ["", self._calibration_line(predictions, outcomes)]
        return "\n".join(lines)

    def _overall_rpm(self) -> float:
        """全体の1,000インプあたり収益。"""
        best: dict[str, tuple[int, int]] = {}
        for row in self.rows("outcome"):
            slug = row.get("niche_slug", "")
            m = row.get("metrics", {})
            impressions = int(m.get("impressions") or 0)
            revenue = int(m.get("revenue_jpy", 0))
            prev = best.get(slug, (0, 0))
            best[slug] = (max(prev[0], impressions), max(prev[1], revenue))
        impressions_total = sum(i for i, _ in best.values())
        revenue_total = sum(r for _, r in best.values())
        return round(revenue_total / impressions_total * 1000, 1) if impressions_total else 0.0

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
                "monetization_source": p.get("monetization_source", ""),
                "actual_rpm": round(FunnelMetrics(**{
                    k: v for k, v in m.items()
                    if k in FunnelMetrics.__dataclass_fields__}).rpm, 1) if m else 0.0,
                "actual_revenue": m.get("revenue_jpy", 0),
                "actual_stage": o.get("stage", 0),
                "mapping_version": p.get("mapping_version", ""),
            })
        return table
