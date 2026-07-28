"""下書きジェネレータのテスト。"""
from __future__ import annotations

import json
from pathlib import Path

from src.drafts.generator import DraftGenerator, Topic, write_pack


def _topic() -> Topic:
    return Topic(
        id="test-topic",
        category="money",
        title="テストのお金ネタ",
        hook="知らないと損する話です",
        key_points=["ポイントA", "ポイントB", "ポイントC", "ポイントD"],
        takeaway="まずは月1万円から。",
        angle="制度変更をやさしく解説",
        sources=[{"title": "出典1", "url": "https://example.com/1"}],
        disclaimers=["投資は自己責任で。"],
    )


def test_generate_produces_full_pack():
    pack = DraftGenerator().generate(_topic())

    # タイトル案は3つ
    assert len(pack.title_ideas) == 3
    # 台本はフック + 要点(最大3) + 結論 + CTA = 6 ビート
    assert len(pack.script.slides) == 6
    assert len(pack.script.slides) == len(pack.script.narration)
    # 出典URLがスクリプトに引き継がれる
    assert "https://example.com/1" in pack.script.source_urls
    # Markdown に主要セクションが含まれる
    for section in ["## タイトル案", "## 台本", "## 概要欄", "## 出典", "## 免責"]:
        assert section in pack.markdown
    # 免責がちゃんと出る
    assert "投資は自己責任で。" in pack.markdown


def test_generate_from_file_and_write(tmp_path: Path):
    topics_file = tmp_path / "2026-01-01.json"
    topics_file.write_text(
        json.dumps({"date": "2026-01-01", "topics": [_topic().__dict__]},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    packs = DraftGenerator().generate_from_file(topics_file)
    assert len(packs) == 1

    out = tmp_path / "out"
    paths = write_pack(packs[0], out)
    assert paths["markdown"].exists()
    assert paths["storyboard"].exists()
    sb = json.loads(paths["storyboard"].read_text(encoding="utf-8"))
    assert sb["slides"]


def test_empty_key_points_falls_back_to_title():
    t = _topic()
    t.key_points = []
    pack = DraftGenerator().generate(t)
    # 要点が無くてもクラッシュせず、フック+結論+CTA が最低限出る
    assert len(pack.script.slides) >= 2
    assert pack.title_ideas[0]
