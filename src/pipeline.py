"""パイプライン全体のオーケストレーションと CLI。

サブコマンド:
  run       収集→分類→安全性→スクリプト→動画→レビューキュー投入
  review    レビューキューの一覧 / 承認 / 却下
  publish   承認済みアイテムを TikTok へ投稿
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import Config, OUTPUT_DIR, ROOT
from .collectors.twitter import TwitterCollector
from .processing.classifier import Classifier
from .processing.safety import SafetyChecker
from .processing.summarizer import Summarizer
from .video.builder import VideoBuilder
from .publishers.review_queue import ReviewQueue
from .publishers.tiktok import TikTokPublisher
from .drafts.generator import DraftGenerator, write_pack

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

    def run(self, limit: int = 10, use_sample: bool | None = None) -> list[str]:
        """収集から動画生成・レビュー投入まで。生成した item_id のリストを返す。"""
        collected = self.collector.collect(use_sample=use_sample)
        topics = self.classifier.build_topics(collected)
        topics = self.safety.filter_topics(topics)[:limit]

        item_ids: list[str] = []
        for topic in topics:
            script = self.summarizer.build_script(topic)
            item_id = f"{topic.category}-{topic.tweets[0].id}"
            out_path = OUTPUT_DIR / f"{item_id}.mp4"
            video_path = self.video.build(script, out_path)
            self.queue.enqueue(item_id, script, video_path, topic.safety_flags)
            item_ids.append(item_id)

        logger.info("run 完了: %d 件をレビューキューに投入", len(item_ids))
        return item_ids

    def publish_approved(self) -> list[dict]:
        """承認済みアイテムを投稿。REVIEW_REQUIRED=false なら pending も対象。"""
        statuses = ["approved"] if self.config.review_required else ["approved", "pending"]
        results: list[dict] = []
        for status in statuses:
            for item in self.queue.list_items(status=status):
                video_path = Path(item.video_path)
                from .models import VideoScript
                script = VideoScript(**item.script)
                result = self.publisher.publish(video_path, script)
                results.append({"id": item.id, "result": result})
                if not self.config.dry_run:
                    self.queue.set_status(item.id, "published")
        logger.info("publish 完了: %d 件", len(results))
        return results


# ---------------------------------------------------------------------------
def _cmd_run(args) -> None:
    Pipeline().run(limit=args.limit, use_sample=args.sample)


def _cmd_drafts(args) -> None:
    """topics/<日付>.json から下書き台本パックを生成し content/<日付>/ に出力。

    有料 API 不要。Claude がリサーチした JSON さえあれば動く中核コマンド。
    """
    topics_path = Path(args.topics)
    if not topics_path.is_absolute():
        topics_path = ROOT / topics_path
    if not topics_path.exists():
        raise SystemExit(f"topics ファイルが見つかりません: {topics_path}")

    date_stem = topics_path.stem
    out_dir = Path(args.out) if args.out else (ROOT / "content" / date_stem)

    cfg = Config.load()
    pub = cfg.section("publishing")
    hashtags = pub.get("hashtags_by_category") if isinstance(pub, dict) else None
    generator = DraftGenerator(hashtags_by_category=hashtags)

    packs = generator.generate_from_file(topics_path)
    index_lines = [f"# {date_stem} の下書きパック（{len(packs)}本）\n"]
    for pack in packs:
        paths = write_pack(pack, out_dir)
        print(f"生成: {paths['markdown']}")
        index_lines.append(f"- [{pack.title_ideas[0]}](./{paths['markdown'].name})")

    (out_dir / "README.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"\n完了: {len(packs)} 本を {out_dir} に出力しました。")


def _cmd_video(args) -> None:
    """storyboard(JSON) から縦型ショート動画(mp4)を生成。

    ffmpeg があれば mp4、無ければ絵コンテJSONにフォールバック。
    TTS(gTTS) が入っていればナレーション音声、無ければ無音スライド動画になる。
    """
    from .models import VideoScript

    sb_path = Path(args.storyboard)
    if not sb_path.exists():
        raise SystemExit(f"storyboard が見つかりません: {sb_path}")

    data = json.loads(sb_path.read_text(encoding="utf-8"))
    script = VideoScript(**data)

    out_path = Path(args.out) if args.out else sb_path.with_suffix(".mp4")
    builder = VideoBuilder(Config.load())
    result = builder.build(script, out_path)
    print(f"生成: {result}")


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
    Pipeline().publish_approved()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description="Twitter→TikTok 自動化")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="収集〜動画生成〜レビュー投入")
    p_run.add_argument("--limit", type=int, default=10)
    p_run.add_argument("--sample", action="store_true", help="サンプルデータで実行")
    p_run.set_defaults(func=_cmd_run)

    p_dft = sub.add_parser("drafts", help="topics JSON から下書き台本パックを生成（API不要）")
    p_dft.add_argument("--topics", required=True,
                       help="例: data/topics/2026-07-28.json")
    p_dft.add_argument("--out", default=None, help="出力先（既定: content/<日付>/）")
    p_dft.set_defaults(func=_cmd_drafts)

    p_vid = sub.add_parser("video", help="storyboard JSON から縦型mp4を生成")
    p_vid.add_argument("--storyboard", required=True,
                       help="例: content/2026-07-28/ideco-2026-kaisei.storyboard.json")
    p_vid.add_argument("--out", default=None, help="出力mp4パス（既定: 同名.mp4）")
    p_vid.set_defaults(func=_cmd_video)

    p_rev = sub.add_parser("review", help="レビューキュー操作")
    p_rev.add_argument("--list", dest="_list", action="store_true")
    p_rev.add_argument("--status", default=None, help="pending/approved/rejected で絞り込み")
    p_rev.add_argument("--approve", metavar="ITEM_ID")
    p_rev.add_argument("--reject", metavar="ITEM_ID")
    p_rev.set_defaults(func=_cmd_review)

    p_pub = sub.add_parser("publish", help="承認済みを TikTok へ投稿")
    p_pub.add_argument("--approved", action="store_true")
    p_pub.set_defaults(func=_cmd_publish)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
