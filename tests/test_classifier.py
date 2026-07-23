from src.config import Config
from src.models import Tweet
from src.processing.classifier import Classifier


def _config():
    cfg = Config.load()
    cfg.raw["classification"] = {
        "weights": {"likes": 0.3, "retweets": 0.5, "replies": 0.2},
        "score_threshold": 200,
    }
    return cfg


def test_score_tweet():
    clf = Classifier(_config())
    tweet = Tweet(id="1", text="x", author="a", likes=1000, retweets=200, replies=50)
    # 1000*0.3 + 200*0.5 + 50*0.2 = 300 + 100 + 10 = 410
    assert clf.score_tweet(tweet) == 410.0


def test_threshold_filters_low_engagement():
    clf = Classifier(_config())
    low = Tweet(id="1", text="低い", author="a", likes=10, retweets=1, replies=0)
    high = Tweet(id="2", text="高い話題。詳細はこちら", author="b",
                 likes=2000, retweets=500, replies=100)
    topics = clf.build_topics({"enjou": [low, high]})
    assert len(topics) == 1
    assert topics[0].tweets[0].id == "2"


def test_topics_sorted_by_score():
    clf = Classifier(_config())
    a = Tweet(id="a", text="A", author="a", likes=1000, retweets=100, replies=10)
    b = Tweet(id="b", text="B", author="b", likes=5000, retweets=1000, replies=200)
    topics = clf.build_topics({"tax": [a, b]})
    assert [t.tweets[0].id for t in topics] == ["b", "a"]
