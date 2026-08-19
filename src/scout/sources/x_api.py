"""X API v2 による「需要の兆候」収集。

ちゃっぴー案では発掘を Grok に任せていたが、Grok は有料 API で、しかも
「何が伸びているか」の判断が LLM の主観になる。X API から直接取ると
**エンゲージメント速度（いいね/経過時間）が実測できる**ので、両方使う。

狙うのは人気ランキングではなく需要の兆候。「〜が欲しい」「〜で困ってる」
「〜ないの?」という言い方は、まだ供給が無い市場のシグナルとして機能する。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from ...config import Config
from ...models import Tweet
from ..models import Candidate

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class XApiSource:
    name = "x_api"

    def __init__(self, config: Config):
        self.config = config
        self.token = config.x_bearer_token
        scout = config.section("scout")
        self.queries: dict[str, str] = scout.get("discovery_queries", {}) or {}
        self.min_likes = int(scout.get("min_likes", 30))
        self.max_results = int(scout.get("max_results_per_query", 25))

    @property
    def available(self) -> bool:
        return bool(self.token and self.queries)

    def discover(self, limit: int) -> list[Candidate]:
        if not self.available:
            logger.info("X_BEARER_TOKEN 未設定のため x_api 発掘をスキップします。")
            return []

        candidates: list[Candidate] = []
        for intent, query in self.queries.items():
            for tweet in self._search(query):
                velocity = self._velocity(tweet)
                candidates.append(Candidate(
                    title=self._headline(tweet.text),
                    summary=tweet.text.strip(),
                    source=self.name,
                    keywords=[intent],
                    evidence_urls=[tweet.url] if tweet.url else [],
                    signals={
                        "intent": intent,
                        "likes": tweet.likes,
                        "retweets": tweet.retweets,
                        "replies": tweet.replies,
                        # 「伸び始めている」の実測値。総いいね数より重要。
                        "likes_per_hour": velocity,
                        "author_verified": tweet.author_verified,
                    },
                ))

        # 総量ではなく伸びの速さで並べる
        candidates.sort(key=lambda c: c.signals.get("likes_per_hour", 0), reverse=True)
        return candidates[:limit]

    # ------------------------------------------------------------------
    def _search(self, query: str) -> list[Tweet]:
        params = {
            "query": query,
            "max_results": max(10, min(self.max_results, 100)),
            "tweet.fields": "public_metrics,created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username,verified",
        }
        try:
            resp = requests.get(SEARCH_URL, headers={"Authorization": f"Bearer {self.token}"},
                                params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("X API の検索に失敗しました: %s", exc)
            return []

        payload = resp.json()
        users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
        tweets: list[Tweet] = []
        for item in payload.get("data", []):
            metrics = item.get("public_metrics", {})
            if metrics.get("like_count", 0) < self.min_likes:
                continue
            user = users.get(item.get("author_id"), {})
            tweets.append(Tweet(
                id=item["id"],
                text=item["text"],
                author=user.get("username", "unknown"),
                author_verified=bool(user.get("verified", False)),
                likes=metrics.get("like_count", 0),
                retweets=metrics.get("retweet_count", 0),
                replies=metrics.get("reply_count", 0),
                created_at=item.get("created_at", ""),
                url=f"https://twitter.com/i/web/status/{item['id']}",
            ))
        return tweets

    @staticmethod
    def _velocity(tweet: Tweet) -> float:
        """いいね/時間。投稿からの経過時間が取れなければ総数をそのまま返す。"""
        if not tweet.created_at:
            return float(tweet.likes)
        try:
            created = datetime.fromisoformat(tweet.created_at.replace("Z", "+00:00"))
        except ValueError:
            return float(tweet.likes)
        hours = max(1.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600)
        return round(tweet.likes / hours, 1)

    @staticmethod
    def _headline(text: str) -> str:
        cleaned = " ".join(text.split())
        for sep in ("。", "！", "？", "\n"):
            idx = cleaned.find(sep)
            if 0 < idx <= 50:
                return cleaned[:idx]
        return cleaned[:50]
