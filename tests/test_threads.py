"""Threads 投稿ビルダーとパブリッシャーのテスト（DRY_RUN）。"""
import os

from src.config import Config
from src.models import Topic, Tweet
from src.processing.summarizer import Summarizer
from src.publishers.threads import ThreadsPublisher


def _config():
    cfg = Config.load()
    cfg.raw["threads"] = {
        "max_chars": 500,
        "cta": "フォローお願いします",
        "hashtags": ["#AI活用", "#副業"],
    }
    return cfg


def _topic(text="新しい税制改正案が公表されました", flags=None):
    return Topic(
        category="tax",
        headline=text[:20],
        score=500,
        tweets=[Tweet(id="1", text=text, author="a", url="https://example.com/1")],
        safety_flags=flags or [],
    )


def test_build_thread_has_hook_body_cta():
    post = Summarizer(_config()).build_thread(_topic())
    assert post.hook
    assert post.body
    assert post.cta == "フォローお願いします"
    assert post.hashtags == ["#AI活用", "#副業"]


def test_render_respects_max_chars():
    cfg = _config()
    cfg.raw["threads"]["max_chars"] = 30
    post = Summarizer(cfg).build_thread(_topic("あ" * 200))
    assert len(post.render(max_chars=30)) <= 30


def test_unverified_flag_surfaces_in_body():
    post = Summarizer(_config()).build_thread(_topic(flags=["unverified_claim"]))
    assert "未確認" in post.body


def test_publisher_dry_run_returns_text_without_api():
    os.environ["DRY_RUN"] = "true"
    cfg = _config()
    cfg.dry_run = True
    post = Summarizer(cfg).build_thread(_topic())
    result = ThreadsPublisher(cfg).publish(post)
    assert result["dry_run"] is True
    assert result["text"]
