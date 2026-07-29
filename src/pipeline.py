"""パイプライン全体のオーケストレーションと CLI。

サブコマンド:
  run       収集→分類→安全性→スクリプト→動画→レビューキュー投入
  review    レビューキューの一覧 / 承認 / 却下
  publish   承認済みアイテムを TikTok へ投稿
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import Config, OUTPUT_DIR
from .collectors.twitter import TwitterCollector
from .processing.classifier import Classifier
from .processing.safety import SafetyChecker
from .processing.summarizer import Summarizer
from .video.builder import VideoBuilder
from .publishers.review_queue import ReviewQueue
from .publishers.tiktok import TikTokPublisher
from .publishers.threads import ThreadsPublisher

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline")


class Pipeline:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.collector = TwitterCollector(self.config)
        self.classifier = Classifier(self.config)
        self.safety = SafetyChecker(self.config)
        self.summarizer = Summarizer(self.config)
        self.video = VideoBuilder(self.config)
        self.queue = ReviewQueue()
        self.publisher = TikTokPublisher(self.config)
        self.threads_publisher = ThreadsPublisher(self.config)

    def run(self, limit: int = 10, use_sample: bool | None = None) -> list[str]:
        """収集から動画生成・レビュー投入まで。生成した item_id のリストを返す。"""
        collected = self.collector.collect(use_sample=use_sample)
        topics = self.classifier.build_topics(collected)
        topics = self.safety.filter_topics(topics)[:limit]

        item_ids: list[str] = []
        for topic in topics:
            script = self.summarizer.build_script(topic)
            thread_post = self.summarizer.build_thread(topic)
            item_id = f"{topic.category}-{topic.tweets[0].id}"
            out_path = OUTPUT_DIR / f"{item_id}.mp4"
            video_path = self.video.build(script, out_path)
            self.queue.enqueue(item_id, script, video_path, topic.safety_flags,
                               thread_post=thread_post)
            item_ids.append(item_id)

        logger.info("run 完了: %d 件をレビューキューに投入", len(item_ids))
        return item_ids

    def publish_approved(self, target: str = "tiktok") -> list[dict]:
        """承認済みアイテムを投稿。REVIEW_REQUIRED=false なら pending も対象。

        target: "tiktok"（動画）または "threads"（テキスト）。
        """
        statuses = ["approved"] if self.config.review_required else ["approved", "pending"]
        results: list[dict] = []
        for status in statuses:
            for item in self.queue.list_items(status=status):
                if target == "threads":
                    from .models import ThreadsPost
                    if not item.thread_post:
                        logger.warning("Threads 投稿データがありません: %s", item.id)
                        continue
                    post = ThreadsPost(**item.thread_post)
                    result = self.threads_publisher.publish(post)
                else:
                    from .models import VideoScript
                    script = VideoScript(**item.script)
                    result = self.publisher.publish(Path(item.video_path), script)
                results.append({"id": item.id, "result": result})
                if not self.config.dry_run:
                    self.queue.set_status(item.id, "published")
        logger.info("publish 完了 (%s): %d 件", target, len(results))
        return results


# ---------------------------------------------------------------------------
def _cmd_run(args) -> None:
    Pipeline().run(limit=args.limit, use_sample=args.sample)


def _cmd_review(args) -> None:
    queue = ReviewQueue()
    if args.approve:
        queue.approve(args.approve)
    elif args.reject:
        queue.reject(args.reject)
    else:
        items = queue.list_items(status=args.status)
        if not items:
            print("（キューは空です）")
        for it in items:
            flags = ",".join(it.safety_flags) or "-"
            print(f"[{it.status}] {it.id}  flags={flags}")
            print(f"    title: {it.script.get('title')}")
            print(f"    video: {it.video_path}")


def _cmd_publish(args) -> None:
    Pipeline().publish_approved(target=args.target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description="Twitter→TikTok 自動化")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="収集〜動画生成〜レビュー投入")
    p_run.add_argument("--limit", type=int, default=10)
    p_run.add_argument("--sample", action="store_true", help="サンプルデータで実行")
    p_run.set_defaults(func=_cmd_run)

    p_rev = sub.add_parser("review", help="レビューキュー操作")
    p_rev.add_argument("--list", dest="_list", action="store_true")
    p_rev.add_argument("--status", default=None, help="pending/approved/rejected で絞り込み")
    p_rev.add_argument("--approve", metavar="ITEM_ID")
    p_rev.add_argument("--reject", metavar="ITEM_ID")
    p_rev.set_defaults(func=_cmd_review)

    p_pub = sub.add_parser("publish", help="承認済みを TikTok / Threads へ投稿")
    p_pub.add_argument("--approved", action="store_true")
    p_pub.add_argument("--target", choices=["tiktok", "threads"], default="tiktok",
                       help="投稿先（既定: tiktok）")
    p_pub.set_defaults(func=_cmd_publish)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
