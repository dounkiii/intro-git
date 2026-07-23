"""安全性ガードレール。

炎上ネタは特定個人への攻撃や誤情報の拡散につながりやすい。
このモジュールは各トピックにリスクフラグを付け、危険度の高いものはブロックする。
判断はヒューリスティックであり、最終判断は人間のレビュー（review_queue）で行う想定。
"""
from __future__ import annotations

import logging
import re

from ..config import Config
from ..models import Topic

logger = logging.getLogger(__name__)

# 断定的・扇動的な未確認表現（誤情報リスク）
UNVERIFIED_PATTERNS = [
    r"確定", r"間違いない", r"crimes?", r"逮捕", r"犯罪", r"不倫", r"薬物",
    r"デマ確定", r"黒確", r"クロ確",
]

# 個人攻撃・差別を示唆する表現
ABUSIVE_PATTERNS = [
    r"死ね", r"殺す", r"消えろ", r"バカ", r"アホ", r"クズ", r"ブス",
    r"追い込め", r"晒せ", r"特定しろ",
]

# 個人名らしき「さん/氏」付き固有名詞（フルネーム名指しの簡易検出）
PERSONAL_NAME = re.compile(r"[一-龥ぁ-んァ-ヶA-Za-z]{2,}(さん|氏|容疑者)")


class SafetyChecker:
    def __init__(self, config: Config):
        cfg = config.section("safety")
        self.block_personal_targeting = bool(cfg.get("block_personal_targeting", True))
        self.flag_unverified = bool(cfg.get("flag_unverified_claims", True))
        self.prefer_verified = bool(cfg.get("prefer_verified_sources", True))

    def review(self, topic: Topic) -> Topic:
        text = " ".join(t.text for t in topic.tweets)
        flags: list[str] = []

        if self._matches(text, ABUSIVE_PATTERNS):
            flags.append("abusive_language")
            topic.blocked = True

        if self.block_personal_targeting and PERSONAL_NAME.search(text):
            flags.append("personal_targeting")
            topic.blocked = True

        if self.flag_unverified and self._matches(text, UNVERIFIED_PATTERNS):
            flags.append("unverified_claim")
            # ブロックはしないが、レビュー必須の警告

        if self.prefer_verified and not any(t.author_verified for t in topic.tweets):
            flags.append("no_verified_source")

        topic.safety_flags = flags
        if topic.blocked:
            logger.warning("topic blocked (%s): %s", ",".join(flags), topic.headline)
        return topic

    def filter_topics(self, topics: list[Topic]) -> list[Topic]:
        """全トピックにレビューを適用。ブロックされていないものだけ返す。"""
        reviewed = [self.review(t) for t in topics]
        allowed = [t for t in reviewed if not t.blocked]
        logger.info("safety: %d allowed / %d blocked", len(allowed), len(reviewed) - len(allowed))
        return allowed

    @staticmethod
    def _matches(text: str, patterns: list[str]) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)
