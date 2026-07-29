"""Threads API（Meta Graph API）によるテキスト投稿。

参考: https://developers.facebook.com/docs/threads/

投稿は 2 ステップ:
  1. コンテナ作成:  POST {THREADS_USER_ID}/threads   (media_type=TEXT, text=...)
  2. 公開:          POST {THREADS_USER_ID}/threads_publish  (creation_id=...)

注意:
- `DRY_RUN=true` の間は API を呼ばず、投稿内容をログ出力するだけ。
- Threads/Meta の利用規約・自動化の上限を遵守すること（過度な自動投稿は凍結リスク）。
"""
from __future__ import annotations

import logging

import requests

from ..config import Config
from ..models import ThreadsPost

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.threads.net/v1.0"


class ThreadsPublisher:
    def __init__(self, config: Config):
        self.config = config
        self.token = config.threads_access_token
        self.user_id = config.threads_user_id
        threads_cfg = config.section("threads")
        self.max_chars = int(threads_cfg.get("max_chars", 500))

    def publish(self, post: ThreadsPost) -> dict:
        """Threads にテキスト投稿する。DRY_RUN 時は送信内容を返すだけ。"""
        text = post.render(max_chars=self.max_chars)

        if self.config.dry_run:
            logger.info("[DRY_RUN] Threads 投稿スキップ:\n%s", text)
            return {"dry_run": True, "text": text}

        if not self.token or not self.user_id:
            raise RuntimeError("THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定です")

        creation_id = self._create_container(text)
        result = self._publish_container(creation_id)
        logger.info("Threads へ投稿しました: %s", post.hook)
        return result

    def _create_container(self, text: str) -> str:
        resp = requests.post(
            f"{GRAPH_BASE}/{self.user_id}/threads",
            data={"media_type": "TEXT", "text": text, "access_token": self.token},
            timeout=30,
        )
        resp.raise_for_status()
        creation_id = resp.json().get("id")
        if not creation_id:
            raise RuntimeError(f"コンテナ作成に失敗しました: {resp.text}")
        return creation_id

    def _publish_container(self, creation_id: str) -> dict:
        resp = requests.post(
            f"{GRAPH_BASE}/{self.user_id}/threads_publish",
            data={"creation_id": creation_id, "access_token": self.token},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
