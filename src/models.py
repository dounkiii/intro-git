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

    category: str          # config.yaml の collection.queries のキー
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
    hook: str = ""              # 冒頭2秒のフック（離脱率を決める）
    generated_by: str = "template"   # "claude" | "template"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Article:
    """アフィリエイト記事（note / ブログ用）。動画より先に金になる主収益源。

    docs/PLAYBOOK.md「8. アフィリエイト・ファースト」参照。動画は集客、
    換金はこの記事とプロフィール導線で行う。
    """

    topic_category: str
    title: str
    body_markdown: str = ""
    monetization_route: str = "なし"   # 承認カードに出す換金経路サマリ
    source_urls: list[str] = field(default_factory=list)
    generated_by: str = "template"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
