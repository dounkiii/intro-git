from src.config import Config
from src.models import Topic, Tweet
from src.processing.safety import SafetyChecker


def _config():
    cfg = Config.load()
    cfg.raw["safety"] = {
        "block_personal_targeting": True,
        "flag_unverified_claims": True,
        "prefer_verified_sources": True,
    }
    return cfg


def _topic(text, verified=True):
    return Topic(
        category="enjou",
        headline=text[:20],
        score=500,
        tweets=[Tweet(id="1", text=text, author="a", author_verified=verified)],
    )


def test_blocks_abusive_language():
    checker = SafetyChecker(_config())
    topic = checker.review(_topic("あいつは消えろ、許せない"))
    assert topic.blocked
    assert "abusive_language" in topic.safety_flags


def test_blocks_personal_targeting():
    checker = SafetyChecker(_config())
    topic = checker.review(_topic("山田太郎さんが問題発言をした"))
    assert topic.blocked
    assert "personal_targeting" in topic.safety_flags


def test_flags_unverified_but_not_blocked():
    checker = SafetyChecker(_config())
    topic = checker.review(_topic("この件は犯罪で間違いないという投稿が拡散"))
    # 未確認の断定表現はフラグを立てるが、ブロックはしない（人間レビューで判断）
    assert "unverified_claim" in topic.safety_flags
    assert not topic.blocked


def test_clean_topic_passes():
    checker = SafetyChecker(_config())
    topic = checker.review(_topic("新しい税制改正案が公表されました"))
    assert not topic.blocked
    assert topic.safety_flags == []


def test_filter_topics_removes_blocked():
    checker = SafetyChecker(_config())
    clean = _topic("増税に関する解説が話題です")
    bad = _topic("死ねと書かれた投稿が拡散")
    allowed = checker.filter_topics([clean, bad])
    assert len(allowed) == 1
    assert allowed[0] is clean
