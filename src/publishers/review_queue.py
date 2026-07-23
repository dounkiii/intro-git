"""人間レビュー用のキュー。

生成済み動画とスクリプトを JSON として `data/review_queue/` に保存し、
承認 (approve) されたものだけを投稿対象にする。
炎上・税金という機微なテーマを扱うため、既定でこのゲートを通す。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from ..config import REVIEW_DIR
from ..models import VideoScript

logger = logging.getLogger(__name__)


@dataclass
class ReviewItem:
    id: str
    status: str          # "pending" | "approved" | "rejected"
    script: dict
    video_path: str
    safety_flags: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class ReviewQueue:
    def __init__(self, directory: Path = REVIEW_DIR):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, item_id: str, script: VideoScript, video_path: Path,
                safety_flags: list[str]) -> ReviewItem:
        item = ReviewItem(
            id=item_id,
            status="pending",
            script=script.to_dict(),
            video_path=str(video_path),
            safety_flags=safety_flags,
        )
        self._path(item_id).write_text(
            json.dumps(item.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("レビューキューに追加: %s (flags=%s)", item_id, safety_flags)
        return item

    def list_items(self, status: str | None = None) -> list[ReviewItem]:
        items: list[ReviewItem] = []
        for f in sorted(self.dir.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            item = ReviewItem(**data)
            if status is None or item.status == status:
                items.append(item)
        return items

    def set_status(self, item_id: str, status: str) -> ReviewItem | None:
        path = self._path(item_id)
        if not path.exists():
            logger.warning("レビューアイテムが見つかりません: %s", item_id)
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = status
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("ステータス変更: %s -> %s", item_id, status)
        return ReviewItem(**data)

    def approve(self, item_id: str) -> ReviewItem | None:
        return self.set_status(item_id, "approved")

    def reject(self, item_id: str) -> ReviewItem | None:
        return self.set_status(item_id, "rejected")

    def _path(self, item_id: str) -> Path:
        safe = item_id.replace("/", "_")
        return self.dir / f"{safe}.json"
