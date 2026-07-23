"""TikTok Content Posting API による動画投稿。

参考: https://developers.tiktok.com/doc/content-posting-api-get-started/

注意:
- アプリが未審査の場合、`privacy_level` は SELF_ONLY（本人のみ）に制限される。
- 直接ファイルアップロード（FILE_UPLOAD）は動画バイナリを分割送信する必要がある。
- `DRY_RUN=true` の間は API を呼ばず、投稿内容をログ出力するだけ。
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from ..config import Config
from ..models import VideoScript

logger = logging.getLogger(__name__)

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"


class TikTokPublisher:
    def __init__(self, config: Config):
        self.config = config
        self.token = config.tiktok_access_token
        pub = config.section("publishing")
        self.privacy_level = pub.get("privacy_level", "SELF_ONLY")
        self.disable_comment = bool(pub.get("disable_comment", False))
        self.disable_duet = bool(pub.get("disable_duet", False))
        self.disable_stitch = bool(pub.get("disable_stitch", False))

    def publish(self, video_path: Path, script: VideoScript) -> dict:
        """動画を TikTok に投稿する。DRY_RUN 時は送信内容を返すだけ。"""
        title = self._build_title(script)

        if self.config.dry_run:
            logger.info("[DRY_RUN] 投稿スキップ: %s (%s)", title, video_path)
            return {"dry_run": True, "title": title, "video": str(video_path)}

        if not self.token:
            raise RuntimeError("TIKTOK_ACCESS_TOKEN が未設定です")
        if not video_path.exists() or video_path.suffix != ".mp4":
            raise RuntimeError(f"投稿可能な mp4 がありません: {video_path}")

        size = video_path.stat().st_size
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": self.privacy_level,
                "disable_comment": self.disable_comment,
                "disable_duet": self.disable_duet,
                "disable_stitch": self.disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        resp = requests.post(INIT_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        upload_url = data.get("data", {}).get("upload_url")
        if upload_url:
            self._upload_chunk(upload_url, video_path, size)

        logger.info("TikTok へ投稿しました: %s", title)
        return data

    def _upload_chunk(self, upload_url: str, video_path: Path, size: int) -> None:
        headers = {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        }
        with video_path.open("rb") as fh:
            resp = requests.put(upload_url, data=fh, headers=headers, timeout=120)
        resp.raise_for_status()

    def _build_title(self, script: VideoScript) -> str:
        # TikTok の caption 上限に配慮して切り詰め
        text = script.description or script.title
        return text[:2200]
