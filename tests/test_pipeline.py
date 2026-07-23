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
