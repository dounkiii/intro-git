"""下書き台本パックの生成（初期費用ゼロの中核モジュール）。

`data/topics/<日付>.json`（Claude がその日にリサーチした税金・お金の話題）を入力に、
各トピックについて次を生成する:

  - VideoScript … スライド＋ナレーション（`video.builder` でそのまま動画化できる）
  - Markdown 下書きパック … フック / 台本 / テロップ / YouTubeタイトル案 /
    概要欄 / ハッシュタグ / サムネ文言 / 出典 / 免責 を1枚にまとめた“下書き”

有料 API は一切不要。撮影・編集は生成された台本を見て人が最終チェックする前提。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import VideoScript

logger = logging.getLogger(__name__)

CATEGORY_LABEL = {
    "money": "お金の話",
    "tax": "税金の話",
    "nisa": "投資・NISA",
}

# カテゴリ別の既定ハッシュタグ（config で上書き可能）
DEFAULT_HASHTAGS = {
    "money": ["#お金", "#節税", "#会社員", "#iDeCo", "#新NISA", "#お金の勉強"],
    "tax": ["#税金", "#確定申告", "#副業", "#節税", "#会社員", "#お金の勉強"],
    "nisa": ["#新NISA", "#投資", "#資産運用", "#お金の勉強", "#会社員"],
}


@dataclass
class Topic:
    """リサーチ済みの1話題（下書き1本の元ネタ）。"""

    id: str
    category: str
    title: str
    hook: str
    key_points: list[str]
    takeaway: str = ""
    angle: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    disclaimers: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Topic":
        return cls(
            id=d["id"],
            category=d.get("category", "money"),
            title=d["title"],
            hook=d.get("hook", ""),
            key_points=list(d.get("key_points", [])),
            takeaway=d.get("takeaway", ""),
            angle=d.get("angle", ""),
            sources=list(d.get("sources", [])),
            disclaimers=list(d.get("disclaimers", [])),
        )


@dataclass
class DraftPack:
    """1トピックから生成した下書き一式。"""

    topic_id: str
    category: str
    title_ideas: list[str]
    script: VideoScript
    thumbnail_text: str
    markdown: str


class DraftGenerator:
    """トピック → 下書きパック。テンプレートベースで決定論的（LLM 不要）。"""

    def __init__(self, hashtags_by_category: dict[str, list[str]] | None = None):
        self.hashtags_by_category = hashtags_by_category or DEFAULT_HASHTAGS

    # ------------------------------------------------------------------ public
    def generate(self, topic: Topic) -> DraftPack:
        label = CATEGORY_LABEL.get(topic.category, "お金の話")
        points = topic.key_points or [topic.title]

        slides, narration, roles = self._build_beats(topic, label, points)
        title_ideas = self._title_ideas(topic)
        hashtags = self.hashtags_by_category.get(topic.category, DEFAULT_HASHTAGS["money"])
        description = self._description(topic, hashtags)
        thumbnail = self._thumbnail_text(topic)

        script = VideoScript(
            topic_category=topic.category,
            title=title_ideas[0],
            slides=slides,
            narration=narration,
            description=description,
            source_urls=[s.get("url", "") for s in topic.sources if s.get("url")],
        )
        markdown = self._markdown(topic, label, title_ideas, slides, narration,
                                  roles, description, thumbnail, hashtags)
        return DraftPack(
            topic_id=topic.id,
            category=topic.category,
            title_ideas=title_ideas,
            script=script,
            thumbnail_text=thumbnail,
            markdown=markdown,
        )

    def generate_from_file(self, topics_path: Path) -> list[DraftPack]:
        data = json.loads(Path(topics_path).read_text(encoding="utf-8"))
        topics = [Topic.from_dict(t) for t in data.get("topics", [])]
        return [self.generate(t) for t in topics]

    # ------------------------------------------------------------------ beats
    def _build_beats(self, topic: Topic, label: str,
                     points: list[str]) -> tuple[list[str], list[str], list[str]]:
        """ショート動画の構成（テロップ=slides / 読み上げ=narration / 役割=roles）を作る。

        フック → 要点(最大3) → まとめ → CTA の 6 ビート前後。
        """
        slides: list[str] = []
        narration: list[str] = []
        roles: list[str] = []

        # 0. フック（最初の2秒で掴む）
        slides.append(topic.hook or topic.title)
        narration.append(topic.hook or f"{topic.title}について解説します。")
        roles.append("フック")

        # 1..n. 要点（テロップは短く、ナレーションは自然文に）
        for i, point in enumerate(points[:3], start=1):
            slides.append(f"{i}. {self._short(point, 22)}")
            narration.append(self._sentence(point))
            roles.append(f"要点{i}")

        # まとめ
        if topic.takeaway:
            slides.append("結論")
            narration.append(topic.takeaway)
            roles.append("結論")

        # CTA
        slides.append("保存して後で見返してね\nフォローで最新情報")
        narration.append("参考になったら保存とフォローお願いします。詳しくは概要欄の一次情報もチェックしてください。")
        roles.append("CTA")

        return slides, narration, roles

    # ----------------------------------------------------------------- titles
    def _title_ideas(self, topic: Topic) -> list[str]:
        base = topic.title
        first_point = self._short(topic.key_points[0], 24) if topic.key_points else base
        return [
            f"【知らないと損】{base}",
            f"{base}｜会社員が今やるべきこと",
            f"え、これ知らないの？{first_point}",
        ]

    # ------------------------------------------------------------ description
    def _description(self, topic: Topic, hashtags: list[str]) -> str:
        lines: list[str] = []
        if topic.angle:
            lines.append(topic.angle)
        lines.append("")
        lines.append("【今日のポイント】")
        for p in topic.key_points:
            lines.append(f"・{p}")
        if topic.takeaway:
            lines.append("")
            lines.append(f"▼まとめ\n{topic.takeaway}")
        if topic.sources:
            lines.append("")
            lines.append("【参考・出典（一次情報）】")
            for s in topic.sources:
                lines.append(f"・{s.get('title', '')}\n{s.get('url', '')}")
        if topic.disclaimers:
            lines.append("")
            lines.append("【ご注意】")
            for d in topic.disclaimers:
                lines.append(f"※{d}")
        lines.append("")
        lines.append(" ".join(hashtags))
        return "\n".join(lines).strip()

    def _thumbnail_text(self, topic: Topic) -> str:
        if topic.key_points:
            return self._short(topic.key_points[0], 18)
        return self._short(topic.title, 18)

    # -------------------------------------------------------------- markdown
    def _markdown(self, topic: Topic, label: str, title_ideas: list[str],
                  slides: list[str], narration: list[str], roles: list[str],
                  description: str, thumbnail: str, hashtags: list[str]) -> str:
        beats = []
        for i, (s, n, role) in enumerate(zip(slides, narration, roles)):
            beats.append(
                f"| {i + 1} | {role} | {s.replace(chr(10), ' / ')} | {n} |"
            )
        beats_table = "\n".join(beats)

        titles = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(title_ideas))
        sources = "\n".join(
            f"- [{s.get('title', '')}]({s.get('url', '')})" for s in topic.sources
        ) or "- （出典未設定）"
        disclaimers = "\n".join(f"- {d}" for d in topic.disclaimers) or "- （なし）"
        est_sec = self._estimate_seconds(narration)

        return f"""# 下書き: {title_ideas[0]}

- **カテゴリ**: {label}（`{topic.category}`）
- **ネタID**: `{topic.id}`
- **想定尺**: 約 {est_sec} 秒（YouTube Shorts / TikTok 縦型）
- **狙い**: {topic.angle or topic.title}

## サムネ / 表紙文言
> {thumbnail}

## タイトル案（3つから選ぶ）
{titles}

## 台本（テロップ＝画面表示 / ナレーション＝読み上げ）
| # | 役割 | テロップ | ナレーション |
|---|------|----------|--------------|
{beats_table}

## 概要欄（コピペ用）
```
{description}
```

## ハッシュタグ
{' '.join(hashtags)}

## 出典（一次情報・撮影前に必ず確認）
{sources}

## 免責・注意
{disclaimers}

---
*この下書きは自動生成です。数字・制度は公開日時点のもの。投稿前に一次情報で必ずファクトチェックしてください。*
"""

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _short(text: str, limit: int) -> str:
        text = text.replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @staticmethod
    def _sentence(text: str) -> str:
        text = text.strip()
        if text and text[-1] not in "。！？.!?":
            text += "。"
        return text

    @staticmethod
    def _estimate_seconds(narration: list[str]) -> int:
        """日本語ナレーションの想定尺（およそ 6 文字/秒）。"""
        chars = sum(len(n) for n in narration)
        return max(15, round(chars / 6))


def write_pack(pack: DraftPack, out_dir: Path) -> dict[str, Path]:
    """下書きパックを Markdown と storyboard(JSON) として書き出す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{pack.topic_id}.md"
    sb_path = out_dir / f"{pack.topic_id}.storyboard.json"
    md_path.write_text(pack.markdown, encoding="utf-8")
    sb_path.write_text(
        json.dumps(pack.script.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"markdown": md_path, "storyboard": sb_path}
