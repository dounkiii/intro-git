"""Grok (xAI) による発掘アダプタ。

xAI の API は OpenAI 互換（`https://api.x.ai/v1/chat/completions`, Bearer 認証）。
Grok を残す理由は1つだけ: **X 上の空気を読む部分は他モデルで代替しにくい**。
Web 検索は Claude の web_search で足りるので、Grok には発掘だけをやらせる。

モデル名は変わるので `config.yaml` の `scout.grok.model` で指定する（既定値は
動作しない可能性がある。https://docs.x.ai/ で現行のモデル名を確認して設定する）。
X のリアルタイム検索（Live Search）を使う場合は `scout.grok.extra_body` に
リクエストパラメータを足せば、コードを変更せずに有効化できる。
"""
from __future__ import annotations

import json
import logging
import os

import requests

from ...config import Config
from ..models import Candidate

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.x.ai/v1"

SYSTEM_PROMPT = """あなたは日本語圏の個人向けに、まだ競合が少ない収益機会を探すリサーチャーです。

探すのは人気ランキングではありません。次の条件を満たすものだけを挙げてください。
- 需要が生まれ始めている兆候がある（検索・投稿・質問が増えている）
- にもかかわらず、日本語の供給（記事・動画・商品）がまだ薄い
- 個人がコンテンツかデジタル商品で参入できる

すでに大流行しているテーマ、大手が押さえているテーマは除外してください。
確認できない数値は書かず、根拠となる URL を可能な限り添えてください。"""

RESPONSE_INSTRUCTION = """次の JSON 形式のみで出力してください（前後に説明を書かない）。

{"candidates": [
  {"title": "短い見出し",
   "summary": "何が起きているか2〜3文",
   "keywords": ["検索に使える語", "..."],
   "evidence_urls": ["https://..."],
   "why_early": "なぜ『まだ競合が少ない』と言えるか"}
]}"""


class GrokSource:
    name = "grok"

    def __init__(self, config: Config):
        self.config = config
        grok = config.section("scout").get("grok", {}) or {}
        self.enabled = bool(grok.get("enabled", False))
        self.model = grok.get("model", "grok-4")
        self.base_url = grok.get("base_url", DEFAULT_BASE_URL).rstrip("/")
        self.extra_body: dict = grok.get("extra_body", {}) or {}
        self.topics: list[str] = grok.get("topics", []) or []
        self.api_key = os.getenv("XAI_API_KEY", "").strip()

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        if not self.api_key:
            logger.info("XAI_API_KEY 未設定のため grok 発掘をスキップします。")
            return False
        return True

    def discover(self, limit: int) -> list[Candidate]:
        if not self.available:
            return []

        topics = "、".join(self.topics) if self.topics else "副業・AIツール・お金"
        prompt = (
            f"X（旧Twitter）上の直近1週間の動きから、{topics} の領域で"
            f"「需要が伸び始めているのに日本語の供給が薄い」ネタを {limit} 件挙げてください。\n\n"
            f"{RESPONSE_INSTRUCTION}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            **self.extra_body,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json=payload, timeout=120,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            logger.warning("Grok の呼び出しに失敗しました（%s）。この発掘元をスキップします。",
                           type(exc).__name__)
            return []

        return self._parse(content, limit)

    # ------------------------------------------------------------------
    @staticmethod
    def _parse(content: str, limit: int) -> list[Candidate]:
        """JSON を取り出す。コードフェンスで囲まれて返ることがあるので剥がす。"""
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.lower().startswith("json") else text
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            logger.warning("Grok のレスポンスから JSON を取り出せませんでした。")
            return []

        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            logger.warning("Grok のレスポンスが JSON として読めませんでした。")
            return []

        candidates: list[Candidate] = []
        for entry in (data.get("candidates") or [])[:limit]:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            candidates.append(Candidate(
                title=title,
                summary=(entry.get("summary") or "").strip(),
                source="grok",
                keywords=[k for k in (entry.get("keywords") or []) if k][:8],
                evidence_urls=[u for u in (entry.get("evidence_urls") or []) if u][:5],
                signals={"why_early": (entry.get("why_early") or "").strip()},
            ))
        return candidates
