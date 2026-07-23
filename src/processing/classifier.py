"""トピック分類と話題度スコアリング。

収集したツイート群を category ごとにまとめ、エンゲージメント指標から
「話題度スコア」を計算し、閾値以上のトピックだけを採用する。
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import Topic, Tweet

logger = logging.getLogger(__name__)


class Classifier:
    def __init__(self, config: Config):
        self.config = config
        cls_cfg = config.section("classification")
        self.weights = cls_cfg.get("weights", {"likes": 0.3, "retweets": 0.5, "replies": 0.2})
        self.threshold = float(cls_cfg.get("score_threshold", 0))

    def score_tweet(self, tweet: Tweet) -> float:
        w = self.weights
        return (
            tweet.likes * float(w.get("likes", 0))
            + tweet.retweets * float(w.get("retweets", 0))
            + tweet.replies * float(w.get("replies", 0))
        )

    def build_topics(self, collected: dict[str, list[Tweet]]) -> list[Topic]:
        """カテゴリごとに、話題度の高いツイートを1トピック=1動画として構築。"""
        topics: list[Topic] = []
        for category, tweets in collected.items():
            for tweet in tweets:
                score = self.score_tweet(tweet)
                if score < self.threshold:
                    continue
                topics.append(
                    Topic(
                        category=category,
                        headline=self._headline(tweet),
                        score=round(score, 1),
                        tweets=[tweet],
                    )
                )
        # 話題度の高い順
        topics.sort(key=lambda t: t.score, reverse=True)
        logger.info("built %d topics above threshold=%.0f", len(topics), self.threshold)
        return topics

    @staticmethod
    def _headline(tweet: Tweet) -> str:
        """ツイート本文から簡易的な見出しを作る（最初の句点まで、または40字）。"""
        text = tweet.text.replace("\n", " ").strip()
        for sep in ("。", "！", "？", "#"):
            idx = text.find(sep)
            if 0 < idx <= 40:
                return text[:idx].strip()
        return text[:40].strip()
