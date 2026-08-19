"""SERP の守備力を見る（GPT提案④を採用、ただしデータ源は差し替え可能にした）。

採用した考え方: 「検索結果が何万件あるか」ではなく **TOP10 を倒せるかどうか** を見る。
上位が掲示板・Q&A・個人ブログ・古い記事で埋まっているなら参入余地がある。
逆に公式サイト・大手メディア・EC が並んでいるなら、件数が少なくても入れない。

実装上の判断: 本物の Google SERP（順位・タイトル・更新日）は有料 API か規約違反の
スクレイピングでしか取れない。そこで provider を差し替え式にした。

  heuristic  (既定・無料) Claude の web_search が返した URL とタイトルをドメイン種別に
             分類する代理指標。**confidence を低く固定**し、実測を騙らない
  dataforseo / serpapi    本物の SERP。初売上が出てから有料で入れる（未実装）

代理指標であることを confidence で明示するのが要点。0.45 前後に留めるので、
Discovery Score の合成時に自動的に割り引かれる。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# --- ドメイン種別の判定ルール -------------------------------------------------
# 「倒しやすい」= UGC / 個人ブログ。「倒しにくい」= 公式 / 大手メディア / EC。
UGC_HOSTS = (
    "chiebukuro.yahoo.co.jp", "detail.chiebukuro.yahoo.co.jp", "okwave.jp",
    "oshiete.goo.ne.jp", "5ch.net", "2ch.sc", "reddit.com", "quora.com",
    "teratail.com", "qiita.com", "zenn.dev", "x.com", "twitter.com",
    "girlschannel.net", "mama.st",
)
PERSONAL_BLOG_HOSTS = (
    "hatenablog.com", "hateblo.jp", "hatenadiary.jp", "ameblo.jp",
    "blog.livedoor.jp", "livedoor.blog", "fc2.com", "seesaa.net",
    "blogspot.com", "wordpress.com", "note.com", "muragon.com", "exblog.jp",
)
STRONG_HOSTS = (
    "wikipedia.org", "nikkei.com", "asahi.com", "yomiuri.co.jp", "mainichi.jp",
    "nhk.or.jp", "itmedia.co.jp", "toyokeizai.net", "diamond.jp", "president.jp",
    "bengo4.com", "zeiri4.com", "freee.co.jp", "moneyforward.com", "smbc.co.jp",
    "allabout.co.jp", "mynavi.jp", "recruit.co.jp", "doda.jp", "rakuten-sec.co.jp",
)
EC_HOSTS = ("amazon.co.jp", "amazon.com", "rakuten.co.jp", "kakaku.com",
            "mercari.com", "yahoo-shopping", "shopping.yahoo.co.jp")
# 公式・行政は最も倒しにくい
OFFICIAL_SUFFIXES = (".go.jp", ".lg.jp", ".ac.jp")

_YEAR_RE = re.compile(r"20\d{2}")


def classify_host(url: str) -> str:
    """URL をドメイン種別に分類する。"""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "unknown"
    if any(host.endswith(s) for s in OFFICIAL_SUFFIXES):
        return "official"
    for group, label in ((UGC_HOSTS, "ugc"), (PERSONAL_BLOG_HOSTS, "personal"),
                         (STRONG_HOSTS, "strong"), (EC_HOSTS, "ec")):
        if any(host == h or host.endswith("." + h) for h in group):
            return label
    return "unknown"


@dataclass
class SerpWeakness:
    """SERP の守備力。weakness が高いほど参入余地がある。"""

    weakness: int = 0                  # 0-100
    confidence: float = 0.0
    provider: str = "heuristic"
    sampled: int = 0
    breakdown: dict[str, float] = field(default_factory=dict)
    intent_match_ratio: float = 0.0    # 上位タイトルが検索意図に一致している率
    stale_ratio: float = 0.0           # 古い年号が入っている率
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "weakness": self.weakness, "confidence": self.confidence,
            "provider": self.provider, "sampled": self.sampled,
            "breakdown": self.breakdown, "intent_match_ratio": self.intent_match_ratio,
            "stale_ratio": self.stale_ratio, "notes": self.notes,
        }


class SerpAnalyzer:
    """provider を差し替えて SERP の守備力を測る。"""

    def __init__(self, provider: str = "heuristic", min_sample: int = 5):
        self.provider = provider
        self.min_sample = min_sample

    def analyze(self, results: list[dict], keywords: list[str]) -> SerpWeakness:
        """results は [{"url": ..., "title": ...}, ...]。"""
        if self.provider != "heuristic":
            raise NotImplementedError(
                f"provider={self.provider} は未実装です。初売上が出てから "
                f"有料 SERP API を入れる想定です（docs/RESEARCH_SYSTEM.md）。"
            )
        return self._heuristic(results, keywords)

    # ------------------------------------------------------------------
    def _heuristic(self, results: list[dict], keywords: list[str]) -> SerpWeakness:
        urls = [r.get("url", "") for r in results if r.get("url")]
        if not urls:
            return SerpWeakness(weakness=0, confidence=0.0, sampled=0,
                                notes=["検索結果が0件のため判定不能"])

        counts: dict[str, int] = {}
        for url in urls:
            label = classify_host(url)
            counts[label] = counts.get(label, 0) + 1

        n = len(urls)
        share = {k: round(v / n, 3) for k, v in counts.items()}
        weak = share.get("ugc", 0) + share.get("personal", 0)
        strong = share.get("strong", 0) + share.get("ec", 0) + share.get("official", 0)

        # 0.5 を中立として、倒しやすい側に寄れば上、倒しにくい側に寄れば下
        weakness = round(100 * max(0.0, min(1.0, 0.5 + 0.5 * (weak - strong))))

        intent = self._intent_match(results, keywords)
        stale = self._stale_ratio(results)

        # 上位が検索意図にぴったり合っている = 競合が本気で狙っている → 守備力が高い
        if intent >= 0.6:
            weakness = max(0, weakness - 15)
        # 古い記事ばかり = 更新されていない → 参入余地
        if stale >= 0.4:
            weakness = min(100, weakness + 10)

        confidence, notes = self._confidence(n, share)
        return SerpWeakness(
            weakness=weakness, confidence=confidence, provider="heuristic",
            sampled=n, breakdown=share, intent_match_ratio=intent,
            stale_ratio=stale, notes=notes,
        )

    def _confidence(self, n: int, share: dict[str, float]) -> tuple[float, list[str]]:
        """代理指標なので信頼度は低く抑える。実測を騙らないことが重要。"""
        notes = ["Google の実SERPではなく web_search の結果を分類した代理指標"]
        if n < 3:
            return 0.15, notes + [f"サンプル{n}件では判定できない"]

        confidence = 0.45 if n >= self.min_sample else 0.3
        if n < self.min_sample:
            notes.append(f"サンプル{n}件（推奨{self.min_sample}件以上）")
        unknown = share.get("unknown", 0)
        if unknown >= 0.5:
            confidence = round(confidence * 0.7, 3)
            notes.append(f"未分類ドメインが{unknown:.0%}で分類精度が低い")
        return confidence, notes

    @staticmethod
    def _intent_match(results: list[dict], keywords: list[str]) -> float:
        """上位タイトルにキーワードが含まれている率。"""
        titles = [(r.get("title") or "") for r in results]
        titles = [t for t in titles if t]
        if not titles or not keywords:
            return 0.0
        hits = sum(1 for t in titles if any(k and k in t for k in keywords))
        return round(hits / len(titles), 3)

    @staticmethod
    def _stale_ratio(results: list[dict]) -> float:
        """タイトル/URL に古い年号が入っている率。更新されていない指標。"""
        current = datetime.now(timezone.utc).year
        texts = [f"{r.get('title', '')} {r.get('url', '')}" for r in results]
        dated = [t for t in texts if _YEAR_RE.search(t)]
        if not dated:
            return 0.0
        stale = sum(1 for t in dated
                    if max(int(y) for y in _YEAR_RE.findall(t)) <= current - 2)
        return round(stale / len(dated), 3)


def weakness_to_points(weakness: int, max_points: int) -> int:
    """SERP 守備力 → 「競合の少なさ」の点数。

    この換算は人間が置いた仮説である。Experiment Ledger に mapping_version と
    一緒に記録し、実績が溜まってから校正する（先に正解を考えすぎない）。
    """
    return round(weakness / 100 * max_points)
