"""探索レイヤのデータモデル。

ちゃっぴー案の「スコアリング」を、そのまま LLM に 100 点を答えさせる形にはしていない。
LLM は「競合の少なさ」を推測でしか答えられないため、主観スコア（LLM）と
実測シグナル（検索結果のドメイン数・エンゲージメント速度）を分けて保持し、
両者が食い違ったときに人間へ見せる。詳細は docs/RESEARCH_SYSTEM.md。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

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
    """100点満点の内訳と、実測による補正。"""

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
    # LLM による採点が実際に行われたか。false のときは合計点0を「捨てる」と解釈しない。
    scored: bool = False

    # --- 実測による補正（LLM の自己申告を機械シグナルで殴る） ---
    machine_adjust: int = 0
    adjust_reasons: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def llm_total(self) -> int:
        return sum(getattr(self, k) for k in RUBRIC)

    @property
    def total(self) -> int:
        return max(0, min(100, self.llm_total + self.machine_adjust))

    @property
    def early_signal(self) -> float:
        """本システムの中核指標: 「伸びているのに競合が少ない」度合い。

        単なる合計点だと「すでに大流行しているテーマ」が上位に来てしまう。
        成長性 × 競合の少なさ を別軸で持ち、順位付けはこちらを重く見る。
        """
        growth = self.trend_growth / RUBRIC["trend_growth"]
        room = self.low_competition / RUBRIC["low_competition"]
        return round(growth * room, 3)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(llm_total=self.llm_total, total=self.total, early_signal=self.early_signal)
        return d


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
        score_data = {k: v for k, v in (data.get("score") or {}).items()
                      if k in Score.__dataclass_fields__}
        return cls(
            id=data["id"],
            candidate=Candidate(**(data.get("candidate") or {"title": ""})),
            research=Research(**(data.get("research") or {})),
            score=Score(**score_data),
            verdict=data.get("verdict", "watch"),
            action=data.get("action", ""),
            first_seen=data.get("first_seen", ""),
            last_seen=data.get("last_seen", ""),
            times_seen=int(data.get("times_seen", 1)),
            status=data.get("status", "new"),
        )
