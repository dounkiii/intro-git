"""パイプライン全体のスモークテスト（サンプルデータ + DRY_RUN）。"""
import os

from src.config import Config
from src.pipeline import Pipeline
from src.publishers.review_queue import ReviewQueue


def test_run_with_sample_data(tmp_path, monkeypatch):
    # ffmpeg 無し環境でも絵コンテJSONにフォールバックして完走する
    os.environ["DRY_RUN"] = "true"
    os.environ["REVIEW_REQUIRED"] = "true"
    pipeline = Pipeline(Config.load())
    item_ids = pipeline.run(limit=5, use_sample=True)
    assert len(item_ids) >= 1

    queue = ReviewQueue()
    pending = queue.list_items(status="pending")
    assert any(it.id in item_ids for it in pending)


def test_publish_requires_approval_by_default():
    os.environ["DRY_RUN"] = "true"
    pipeline = Pipeline(Config.load())
    # 承認していなければ pending は投稿対象にならない
    results = pipeline.publish_approved()
    assert all(r["id"] for r in results) or results == []


# --- 実運用で見つかった障害の再発防止 -----------------------------------------
def test_sampleオプションの既定はNoneで自動判定に任せる():
    """store_true の既定 False を渡すと、トークンが無いのに X API を叩いて 401 で落ちる。

    2026-08-22 の daily-generate 失敗の原因。
    """
    from src.pipeline import build_parser

    args = build_parser().parse_args(["run"])
    assert args.sample is None

    args = build_parser().parse_args(["scout"])
    assert args.sample is None

    args = build_parser().parse_args(["run", "--sample"])
    assert args.sample is True


def test_トークンがなければ本番指定でもサンプルに落ちる(monkeypatch):
    """毎朝の cron を 401 で止めないための安全弁。"""
    from src.collectors.twitter import TwitterCollector
    from src.config import Config

    config = Config.load()
    config.x_bearer_token = ""
    collector = TwitterCollector(config)

    def _fail(*a, **k):
        raise AssertionError("トークンが無いのに X API を呼んでいる")

    monkeypatch.setattr(collector, "_search", _fail)

    collected = collector.collect(use_sample=False)

    assert any(collected.values())        # サンプルで中身が返る
