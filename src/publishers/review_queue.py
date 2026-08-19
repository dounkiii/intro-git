"""人間レビュー用のキュー。

生成済み動画とスクリプトを JSON として `data/review_queue/` に保存し、
承認 (approve) されたものだけを投稿対象にする。
炎上・税金という機微なテーマを扱うため、既定でこのゲートを通す。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path

from ..config import REVIEW_DIR
from ..models import Article, VideoScript

logger = logging.getLogger(__name__)


@dataclass
class ReviewItem:
    id: str
    status: str          # "pending" | "approved" | "rejected" | "published"
    script: dict
    video_path: str
    safety_flags: list[str]
    # 以下は後から追加したフィールド。既存の JSON を読めるよう既定値を持たせている。
    category: str = ""
    article: dict = field(default_factory=dict)
    reject_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def flagged(self) -> bool:
        """safety_flags 付き。一括承認の対象から外すための判定。"""
        return bool(self.safety_flags)


class ReviewQueue:
    def __init__(self, directory: Path = REVIEW_DIR):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, item_id: str, script: VideoScript, video_path: Path,
                safety_flags: list[str], category: str = "",
                article: Article | None = None) -> ReviewItem:
        item = ReviewItem(
            id=item_id,
            status="pending",
            script=script.to_dict(),
            video_path=str(video_path),
            safety_flags=safety_flags,
            category=category or script.topic_category,
            article=article.to_dict() if article else {},
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

    def get(self, item_id: str) -> ReviewItem | None:
        path = self._path(item_id)
        if not path.exists():
            return None
        return ReviewItem(**json.loads(path.read_text(encoding="utf-8")))

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

    def reject(self, item_id: str, reason: str = "") -> ReviewItem | None:
        item = self.set_status(item_id, "rejected")
        if item and reason:
            path = self._path(item_id)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["reject_reason"] = reason
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            item.reject_reason = reason
        return item

    def approve_all(self, exclude_flagged: bool = True) -> tuple[list[str], list[str]]:
        """未処理を一括承認する。

        `exclude_flagged=True` のとき safety_flags 付きは承認しない。通勤中に
        雑に一括承認したときに、法務リスクのある案件だけは必ず個別確認させるため。
        戻り値は (承認した item_id, スキップした item_id)。
        """
        approved, skipped = [], []
        for item in self.list_items(status="pending"):
            if exclude_flagged and item.flagged:
                skipped.append(item.id)
                continue
            self.approve(item.id)
            approved.append(item.id)
        logger.info("一括承認: %d件承認 / %d件スキップ", len(approved), len(skipped))
        return approved, skipped

    def _path(self, item_id: str) -> Path:
        safe = item_id.replace("/", "_")
        return self.dir / f"{safe}.json"
