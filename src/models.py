"""パイプライン内で受け渡すデータモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Tweet:
    """収集した1件のツイート。"""

    id: str
    text: str
    author: str
    author_verified: bool = False
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    created_at: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Topic:
    """分類・スコアリング後のトピック（動画1本の元ネタ）。"""

    category: str          # "enjou" | "tax"
    headline: str          # 動画の見出し
    score: float           # 話題度スコア
    tweets: list[Tweet] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    blocked: bool = False  # 安全性チェックで投稿不可と判断された

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tweets"] = [t.to_dict() for t in self.tweets]
        return d


@dataclass
class ThreadsPost:
    """Threads（テキスト主体）への投稿1件。

    Threads は動画前提の TikTok と異なり、テキストの読みやすさと会話性で伸びる。
    そのため「フック（1行目）→ 本文 → CTA」を明確に持たせる。
    """

    topic_category: str
    hook: str = ""                 # スクロールを止める1行目
    body: str = ""                 # 本文（改行区切りの要点）
    cta: str = ""                  # 行動喚起（フォロー/保存/リンク誘導など）
    hashtags: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)

    def render(self, max_chars: int = 500) -> str:
        """実際に投稿するテキストへ組み立てる（文字数上限で切り詰め）。"""
        tags = " ".join(self.hashtags)
        parts = [self.hook, self.body, self.cta, tags]
        text = "\n\n".join(p for p in parts if p)
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1] + "…"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoScript:
    """動画のナレーション/スライド構成。"""

    topic_category: str
    title: str
    slides: list[str] = field(default_factory=list)   # 各スライドの表示テキスト
    narration: list[str] = field(default_factory=list)  # 各スライドの読み上げ文
    description: str = ""       # TikTok 投稿説明文
    source_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
