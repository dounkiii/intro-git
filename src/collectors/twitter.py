"""X (Twitter) API v2 の Recent Search を使ったツイート収集。

Bearer Token が未設定、または `use_sample=True` の場合はサンプルデータを返すため、
API キーがなくてもパイプライン全体を動作確認できる。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from ..config import Config
from ..models import Tweet

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
SAMPLE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sample_tweets.json"


class TwitterCollector:
    def __init__(self, config: Config):
        self.config = config
        self.token = config.x_bearer_token

    def collect(self, use_sample: bool | None = None) -> dict[str, list[Tweet]]:
        """設定された各クエリでツイートを収集し、カテゴリ別に返す。"""
        collection = self.config.section("collection")
        queries: dict[str, str] = collection.get("queries", {})

        if use_sample is None:
            use_sample = not self.token

        results: dict[str, list[Tweet]] = {}
        for category, query in queries.items():
            if use_sample:
                results[category] = self._sample(category)
            else:
                results[category] = self._search(query, collection)
            logger.info("collected %d tweets for category=%s", len(results[category]), category)
        return results

    # ------------------------------------------------------------------
    def _search(self, query: str, collection: dict) -> list[Tweet]:
        max_results = int(collection.get("max_results_per_query", 25))
        params = {
            "query": query,
            "max_results": max(10, min(max_results, 100)),
            "tweet.fields": "public_metrics,created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username,verified",
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
        tweets: list[Tweet] = []
        for item in payload.get("data", []):
            metrics = item.get("public_metrics", {})
            user = users.get(item.get("author_id"), {})
            tweet = Tweet(
                id=item["id"],
                text=item["text"],
                author=user.get("username", "unknown"),
                author_verified=bool(user.get("verified", False)),
                likes=metrics.get("like_count", 0),
                retweets=metrics.get("retweet_count", 0),
                replies=metrics.get("reply_count", 0),
                created_at=item.get("created_at", ""),
                url=f"https://twitter.com/i/web/status/{item['id']}",
            )
            if self._passes_floor(tweet, collection):
                tweets.append(tweet)
        return tweets

    @staticmethod
    def _passes_floor(tweet: Tweet, collection: dict) -> bool:
        return (
            tweet.likes >= int(collection.get("min_likes", 0))
            and tweet.retweets >= int(collection.get("min_retweets", 0))
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _sample(category: str) -> list[Tweet]:
        """API キーなしで動かすためのサンプルデータ。"""
        if SAMPLE_PATH.exists():
            data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
            return [Tweet(**t) for t in data.get(category, [])]
        return []
