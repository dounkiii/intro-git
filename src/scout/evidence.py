"""観測と推測の分離。

GPT からの指摘（採用）: 推測値と実測値を足し引きする（LLM 15点 → 矛盾したら -10）のは
汚い。実測が得られた軸は **LLM 評価を置き換える** べき。

  observed があれば observed を使う / なければ inferred を使い confidence を下げる

矛盾フラグは残す。LLM の推測と現実が大きくズレた軸そのものが、後で配点を
校正するための教師データになるため（docs/RESEARCH_SYSTEM.md「配点は実績に決めさせる」）。

重要な注意: observed → 点数の換算ルール自体は人間が決めた仮説である。
`mapping_version` を必ず記録し、Experiment Ledger と突き合わせて後から校正する。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# observed → 点数の換算ルールの版。ルールを変えたら必ず上げる。
# これが無いと「スコアが変わったのはルール変更のせいか実力のせいか」が判別できない。
MAPPING_VERSION = "2026-08-19.1"

# 推測しか無い軸に与える信頼度。observed が入ると上がる。
INFERRED_CONFIDENCE = 0.3


@dataclass
class Evidence:
    """1つの評価軸に対する根拠。"""

    axis: str
    max_points: int
    inferred: int | None = None      # LLM の推測
    observed: int | None = None      # 実測から換算した点数
    confidence: float = INFERRED_CONFIDENCE
    source: str = "llm"              # "llm" | "x_velocity" | "serp_heuristic" | ...
    mapping_version: str = ""
    note: str = ""

    @property
    def value(self) -> int:
        """採用される点数。実測があれば実測、無ければ推測、両方無ければ0。"""
        if self.observed is not None:
            return self._clamp(self.observed)
        if self.inferred is not None:
            return self._clamp(self.inferred)
        return 0

    @property
    def is_observed(self) -> bool:
        return self.observed is not None

    @property
    def ratio(self) -> float:
        """0.0〜1.0 に正規化した値。Discovery / Business Score の合成に使う。"""
        return self.value / self.max_points if self.max_points else 0.0

    def divergence(self) -> int | None:
        """推測と実測の差。両方ある場合のみ。配点校正の教師データになる。"""
        if self.observed is None or self.inferred is None:
            return None
        return self.observed - self.inferred

    def _clamp(self, v: int) -> int:
        return max(0, min(self.max_points, int(v)))

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(value=self.value, is_observed=self.is_observed,
                 divergence=self.divergence())
        return d


@dataclass
class EvidenceSet:
    """評価軸ごとの根拠の集合。"""

    items: dict[str, Evidence] = field(default_factory=dict)

    def set_inferred(self, axis: str, max_points: int, points: int) -> Evidence:
        ev = self.items.setdefault(axis, Evidence(axis=axis, max_points=max_points))
        ev.max_points = max_points
        ev.inferred = points
        return ev

    def observe(self, axis: str, max_points: int, points: int, source: str,
                confidence: float, note: str = "") -> Evidence:
        """実測値を入れる。推測値は上書きせず残す（差分を教師データにするため）。"""
        ev = self.items.setdefault(axis, Evidence(axis=axis, max_points=max_points))
        ev.max_points = max_points
        ev.observed = points
        ev.source = source
        ev.confidence = confidence
        ev.mapping_version = MAPPING_VERSION
        ev.note = note
        return ev

    def value(self, axis: str) -> int:
        ev = self.items.get(axis)
        return ev.value if ev else 0

    def ratio(self, axis: str) -> float:
        ev = self.items.get(axis)
        return ev.ratio if ev else 0.0

    @property
    def confidence(self) -> float:
        """全軸の平均信頼度。Discovery Score に掛ける（根拠が薄い候補を上げないため）。"""
        if not self.items:
            return 0.0
        return round(sum(e.confidence for e in self.items.values()) / len(self.items), 3)

    @property
    def observed_ratio(self) -> float:
        """実測で埋まった軸の割合。レポートに出して「どこまで測れているか」を可視化する。"""
        if not self.items:
            return 0.0
        return round(sum(1 for e in self.items.values() if e.is_observed) / len(self.items), 3)

    def divergences(self) -> dict[str, int]:
        return {a: d for a, e in self.items.items() if (d := e.divergence()) is not None}

    def to_dict(self) -> dict:
        return {a: e.to_dict() for a, e in self.items.items()}

    @classmethod
    def from_dict(cls, data: dict | None) -> "EvidenceSet":
        items: dict[str, Evidence] = {}
        for axis, raw in (data or {}).items():
            fields = {k: v for k, v in raw.items() if k in Evidence.__dataclass_fields__}
            fields.setdefault("axis", axis)
            fields.setdefault("max_points", 0)
            items[axis] = Evidence(**fields)
        return cls(items=items)
