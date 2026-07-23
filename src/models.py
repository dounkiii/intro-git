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
