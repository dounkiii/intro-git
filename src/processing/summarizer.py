"""動画スクリプト（スライド＋ナレーション）の生成。

既定はテンプレートベースの決定論的生成。`OPENAI_API_KEY` が設定されていれば
LLM による自然な要約に差し替え可能（`_summarize_with_llm` を実装して有効化）。
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import Topic, VideoScript

logger = logging.getLogger(__name__)

CATEGORY_LABEL = {"enjou": "今話題のニュース", "tax": "税金ニュース解説"}


class Summarizer:
    def __init__(self, config: Config):
        self.config = config
        pub = config.section("publishing")
        self.hashtags: list[str] = pub.get("hashtags", [])

    def build_script(self, topic: Topic) -> VideoScript:
        label = CATEGORY_LABEL.get(topic.category, "ニュース")
        tweet = topic.tweets[0]
        body = tweet.text.replace("\n", " ").strip()

        # スライド構成: タイトル → 要点 → 出典 → まとめ
        slides = [
            f"{label}",
            topic.headline,
            self._trim(body, 90),
            "続報は概要欄の一次情報をご確認ください",
            "参考になったらフォローお願いします",
        ]
        narration = [
            f"{label}です。",
            f"{topic.headline}。",
            self._trim(body, 90),
            "詳しい経緯は、公式発表や報道など一次情報をご確認ください。",
            "参考になったらフォローといいねをお願いします。",
        ]

        warn = ""
        if "unverified_claim" in topic.safety_flags:
            warn = "※未確認の情報を含む可能性があります。"
        if "no_verified_source" in topic.safety_flags:
            warn += "（出典は認証アカウント以外を含みます）"

        description = self._build_description(topic, warn)

        return VideoScript(
            topic_category=topic.category,
            title=topic.headline,
            slides=slides,
            narration=narration,
            description=description,
            source_urls=[t.url for t in topic.tweets if t.url],
        )

    def _build_description(self, topic: Topic, warn: str) -> str:
        tags = " ".join(self.hashtags)
        parts = [topic.headline]
        if warn:
            parts.append(warn)
        parts.append("出典はコメント欄/概要をご確認ください。")
        parts.append(tags)
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"

    # LLM を使う場合はここを実装（任意）
    def _summarize_with_llm(self, topic: Topic) -> VideoScript:  # pragma: no cover
        raise NotImplementedError("OPENAI_API_KEY を使った要約は未実装です")
