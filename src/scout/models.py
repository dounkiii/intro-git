"""探索レイヤのデータモデル。

ちゃっぴー案の「スコアリング」を、そのまま LLM に 100 点を答えさせる形にはしていない。
LLM は「競合の少なさ」を推測でしか答えられないため、主観スコア（LLM）と
実測シグナル（検索結果のドメイン数・エンゲージメント速度）を分けて保持し、
両者が食い違ったときに人間へ見せる。詳細は docs/RESEARCH_SYSTEM.md。
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .evidence import EvidenceSet

# ちゃっぴー案の評価軸をそのまま採用（合計100点）
RUBRIC = {
    "demand": 20,              # 需要
    "low_competition": 15,     # 競合の少なさ
    "monetizability": 20,      # 収益性
    "trend_growth": 15,        # トレンド成長性
    "contentability": 10,      # コンテンツ化しやすさ
    "affiliate_fit": 10,       # アフィリエイトとの相性
    "durability": 5,           # 継続性
    "source_reliability": 5,   # 情報の信頼性
}

VERDICTS = ("now", "watch", "drop")   # 今すぐ狙う / 様子見 / 捨てる

# 形態素解析器を入れずに済ませるため、文字種ごとに切り出す。
# ひらがなは助詞・活用が大半でノイズになるので既定では捨てる（「〜の」「〜が終了する」
# まで拾うと、同じネタの言い回し違いが別物と判定されてしまう）。
_ALNUM_RE = re.compile(r"[0-9a-z]+")
_KATAKANA_RE = re.compile(r"[ァ-ヶー]{2,}")
_KANJI_RE = re.compile(r"[一-龥]{2,}")
_HIRAGANA_RE = re.compile(r"[ぁ-ん]{3,}")


def normalize_tokens(*texts: str) -> set[str]:
    """重複判定用のトークン集合。表記ゆれと語順の違いを吸収する。"""
    joined = " ".join(t or "" for t in texts).lower()

    tokens: set[str] = set()
    for pattern in (_ALNUM_RE, _KATAKANA_RE, _KANJI_RE):
        tokens.update(pattern.findall(joined))

    # 漢字・カタカナが1つも取れない場合（ひらがなだけの見出し等）のフォールバック。
    # ここで空集合を返すと slug が全件同一ハッシュになってしまう。
    if not tokens:
        tokens.update(_HIRAGANA_RE.findall(joined))

    return {t for t in tokens if len(t) >= 2}


@dataclass
class Candidate:
    """発掘段階の生ネタ。発掘元（Grok / X API）が返す最小単位。"""

    title: str
    summary: str = ""
    source: str = ""                                  # "grok" | "x_api"
    keywords: list[str] = field(default_factory=list)
    evidence_urls: list[str] = field(default_factory=list)
    # 機械的に取れたシグナル（エンゲージメント速度など）。スコア補正に使う。
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        """安定した ID。同じネタが翌日また出てきたときに同一と判定するため、
        タイトルではなくキーワード集合からハッシュを作る。"""
        basis = "|".join(sorted(normalize_tokens(self.title, " ".join(self.keywords))))
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:10]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Research:
    """裏取り結果。ちゃっぴー案の Gemini 担当分を Claude の web_search で行う。"""

    why_now: str = ""
    jp_demand: str = ""
    overseas_lead: str = ""
    competitor_note: str = ""
    target_user: str = ""
    monetization_paths: list[str] = field(default_factory=list)
    best_product: str = ""
    risks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    # 実測値: 検索で見えた独立ドメイン数など。LLM の自己申告ではない。
    measured: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Score:
    """評価軸ごとの点数と、そこから合成した3つのスコア。

    軸に代入する整数は **LLM の推測値**。実測が入ると `evidence` 側が優先され、
    `total` は実測ベースに切り替わる（推測値は校正用に残る）。

    最終順位は `opportunity` = sqrt(discovery × business)。
    GPT からの指摘（採用）: 「急成長 × 競合ゼロ」でも購買意欲もアフィリ案件も無ければ
    稼げない。逆に金になるテーマでも入る余地がなければ意味がない。積にすることで
    **どちらかがゼロに近い候補を上位に出さない**。
    """

    demand: int = 0
    low_competition: int = 0
    monetizability: int = 0
    trend_growth: int = 0
    contentability: int = 0
    affiliate_fit: int = 0
    durability: int = 0
    source_reliability: int = 0

    llm_verdict: str = "watch"
    rationale: str = ""
    scored: bool = False

    # 観測と推測の分離（src/scout/evidence.py）
    evidence: EvidenceSet = field(default_factory=EvidenceSet)
    # 自前パイプラインで換金経路が組めるか。config と AFF_* から実測する。
    route_available: bool | None = None

    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for axis, max_points in RUBRIC.items():
            self.evidence.set_inferred(axis, max_points, getattr(self, axis))

    # --- 素点 -----------------------------------------------------------
    @property
    def llm_total(self) -> int:
        """LLM の推測だけの合計。実測導入の効果を測るため並列で保持する。"""
        return sum(getattr(self, k) for k in RUBRIC)

    @property
    def total(self) -> int:
        """実測で解決済みの合計。"""
        return sum(self.evidence.value(k) for k in RUBRIC)

    @property
    def confidence(self) -> float:
        return self.evidence.confidence

    @property
    def observed_ratio(self) -> float:
        return self.evidence.observed_ratio

    # --- 合成スコア -----------------------------------------------------
    @property
    def momentum(self) -> float:
        return self.evidence.ratio("trend_growth")

    @property
    def whitespace(self) -> float:
        return self.evidence.ratio("low_competition")

    @property
    def discovery(self) -> float:
        """今入り込む余地があるか（0-100）。

        evidence_confidence を掛けているので、根拠が薄い候補は自動的に割り引かれる。
        実測が1つも無い段階では全候補が等しく割り引かれるため順位は変わらない。
        """
        return round(100 * self.momentum * self.whitespace * self.confidence, 1)

    @property
    def monetization(self) -> float:
        return (self.evidence.ratio("monetizability")
                + self.evidence.ratio("affiliate_fit")) / 2

    @property
    def production_fit(self) -> float:
        """既存の制作パイプラインとの相性。換金経路の有無は実測。"""
        route = 1.0 if self.route_available else (0.2 if self.route_available is False else 0.6)
        return (self.evidence.ratio("contentability")
                + self.evidence.ratio("durability") + route) / 3

    @property
    def business(self) -> float:
        """入った場合に金になるか（0-100）。"""
        return round(100 * self.evidence.ratio("demand")
                     * self.monetization * self.production_fit, 1)

    @property
    def opportunity(self) -> float:
        """最終順位に使うスコア（0-100）。相乗平均なので片方が0なら0。"""
        return round(math.sqrt(max(0.0, self.discovery) * max(0.0, self.business)), 1)

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in RUBRIC}
        d.update(
            llm_verdict=self.llm_verdict, rationale=self.rationale, scored=self.scored,
            route_available=self.route_available,
            conflicts=self.conflicts, notes=self.notes,
            evidence=self.evidence.to_dict(),
            llm_total=self.llm_total, total=self.total,
            confidence=self.confidence, observed_ratio=self.observed_ratio,
            momentum=self.momentum, whitespace=self.whitespace,
            discovery=self.discovery, business=self.business,
            opportunity=self.opportunity,
        )
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> "Score":
        data = data or {}
        fields = {k: v for k, v in data.items()
                  if k in cls.__dataclass_fields__ and k != "evidence"}
        score = cls(**fields)
        restored = EvidenceSet.from_dict(data.get("evidence"))
        if restored.items:
            score.evidence = restored
        return score


@dataclass
class Opportunity:
    """1件の収益機会。JSONL に1行として保存される。"""

    id: str
    candidate: Candidate
    research: Research = field(default_factory=Research)
    score: Score = field(default_factory=Score)
    verdict: str = "watch"
    action: str = ""
    first_seen: str = ""
    last_seen: str = ""
    times_seen: int = 1
    status: str = "new"          # "new" | "adopted" | "dropped"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "candidate": self.candidate.to_dict(),
            "research": self.research.to_dict(),
            "score": self.score.to_dict(),
            "verdict": self.verdict,
            "action": self.action,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "times_seen": self.times_seen,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Opportunity":
        return cls(
            id=data["id"],
            candidate=Candidate(**(data.get("candidate") or {"title": ""})),
            research=Research(**(data.get("research") or {})),
            score=Score.from_dict(data.get("score")),
            verdict=data.get("verdict", "watch"),
            action=data.get("action", ""),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
            times_seen=int(data.get("times_seen", 1)),
            status=data.get("status", "new"),
        )
