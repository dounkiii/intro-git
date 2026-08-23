"""裏取り（ちゃっぴー案の Gemini 担当分）。

Claude の web_search サーバーツールで検索・読解・構造化を 1 リクエストで行う。
Gemini を別途立てないのは、同じ結果を得るのに 3 社目の API キー・課金・
レート制限・SDK 差分を保守する価値がないため（docs/RESEARCH_SYSTEM.md）。

このモジュールは「実測値」も一緒に返す。LLM に「競合は少ないです」と言わせるだけでは
検証にならないので、検索で実際に見えた独立ドメイン数を数えて持ち回る。
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from ..config import Config
from ..llm import ClaudeClient
from .models import Candidate, Research

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは日本語圏の個人向けに収益機会を検証するリサーチャーです。

検証の目的は「面白いか」ではなく「需要が生まれ始めているのに供給がまだ薄いか」です。
- 大手・専門メディアがすでに網羅しているテーマは、はっきり「競合が多い」と書く
- 確認できなかった項目は「不明」と書く。推測で埋めない
- 数値・期限は出典が確認できたものだけ書く
- 日本語圏の状況と、海外が先行しているかを分けて書く"""

PROMPT_TEMPLATE = """次のネタについて Web 検索で裏取りし、下の項目を日本語で埋めてください。

## ネタ
タイトル: {title}
概要: {summary}
検索に使える語: {keywords}
発掘元: {source}
既知の参照: {urls}

## 埋める項目
1. なぜ今なのか（時期的な理由。制度・発表・季節・海外の動き）
2. 日本市場の需要（誰がどれくらい困っているか）
3. 海外の先行状況（先行しているなら何が起きているか。なければ「なし」）
4. 競合コンテンツの量（**必ず実際に検索して**、日本語の記事・動画・商品がどれくらいあるか。
   多いなら正直に「多い」と書く）
5. 想定ユーザー（1文で具体的に）
6. 収益化方法（実現可能な順に3つまで。SEO記事/アフィリ記事/note/有料note/X投稿/
   Xスレッド/YouTube/Shorts/メルマガ/比較サイト/ニッチメディア/テンプレート販売/
   プロンプト販売/リード獲得 から選ぶ）
7. 最もおすすめの作るもの（「これを1本作れば最短で売上になる」を1つだけ）
8. リスク（規約・法規制・一過性・YMYL 評価など。なければ「特になし」）

最後に、参照した URL を箇条書きで列挙してください。"""

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        "jp_demand": {"type": "string"},
        "overseas_lead": {"type": "string"},
        "competitor_note": {"type": "string"},
        "target_user": {"type": "string"},
        "monetization_paths": {"type": "array", "items": {"type": "string"}},
        "best_product": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["why_now", "jp_demand", "overseas_lead", "competitor_note",
                 "target_user", "monetization_paths", "best_product", "risks"],
    "additionalProperties": False,
}


class Researcher:
    def __init__(self, config: Config, llm: ClaudeClient | None = None):
        self.config = config
        self.llm = llm or config.llm_client()
        scout = config.section("scout")
        self.max_searches = int(scout.get("max_searches_per_candidate", 6))
        self.tool_type = scout.get("web_search_tool_type", "web_search_20260209")

    @property
    def available(self) -> bool:
        return self.llm.available

    def investigate(self, candidate: Candidate) -> Research:
        """1件の候補を裏取りする。LLM が使えない場合は空の Research を返す。"""
        known = [{"url": u, "title": ""} for u in candidate.evidence_urls]
        if not self.available:
            # 調査していなくても、発掘元が持っていた URL は実測値として残す
            return Research(competitor_note="未調査（LLM の API キー未設定）",
                            sources=list(candidate.evidence_urls),
                            measured=self.measure(known, candidate.keywords))

        prompt = PROMPT_TEMPLATE.format(
            title=candidate.title,
            summary=candidate.summary or "(なし)",
            keywords=", ".join(candidate.keywords) or "(なし)",
            source=candidate.source,
            urls=", ".join(candidate.evidence_urls) or "(なし)",
        )

        # 1回目: web_search で調査（自由文 + 参照URL）
        found = self.llm.research(SYSTEM_PROMPT, prompt,
                                  max_uses=self.max_searches, tool_type=self.tool_type)
        if found is None:
            # 検索が使えない環境でも、モデルの知識だけで構造化までは進める
            notes, results = "", known
        else:
            notes, found_results = found
            merged = {r["url"]: r for r in known}
            for r in found_results:
                merged.setdefault(r["url"], r)
                if r.get("title"):
                    merged[r["url"]]["title"] = r["title"]
            results = list(merged.values())
        urls = [r["url"] for r in results]

        # 2回目: 構造化。structured outputs はサーバーツールと併用しないよう分けている。
        structured = self.llm.generate_json(
            SYSTEM_PROMPT,
            f"{prompt}\n\n## 調査メモ\n{notes or '(検索できませんでした。既知の情報のみで埋めてください)'}",
            RESEARCH_SCHEMA,
        )
        if structured is None:
            return Research(competitor_note="未調査（生成に失敗）", sources=urls,
                            measured=self.measure(results, candidate.keywords))

        return Research(
            why_now=structured.get("why_now", ""),
            jp_demand=structured.get("jp_demand", ""),
            overseas_lead=structured.get("overseas_lead", ""),
            competitor_note=structured.get("competitor_note", ""),
            target_user=structured.get("target_user", ""),
            monetization_paths=structured.get("monetization_paths", [])[:3],
            best_product=structured.get("best_product", ""),
            risks=structured.get("risks", []),
            sources=urls,
            measured=self.measure(results, candidate.keywords),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def measure(results: list[dict], keywords: list[str] | None = None) -> dict:
        """LLM の自己申告ではない実測値。

        `results`（URL とタイトル）をそのまま持ち回るのが要点。scoring 側が
        SERP のドメイン種別分類（src/scout/serp.py）に使い、「競合の少なさ」の
        点数を LLM の推測から実測へ置き換える。
        """
        domains: set[str] = set()
        for r in results:
            host = urlparse(r.get("url", "")).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                domains.add(host)
        return {
            "evidence_count": len(results),
            "competitor_domains": len(domains),
            "domains": sorted(domains)[:20],
            "results": results[:20],
            "keywords": list(keywords or []),
        }
