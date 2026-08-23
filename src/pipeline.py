"""パイプライン全体のオーケストレーションと CLI。

設計の中心は「生産は全自動、承認だけ人間」。詳細は docs/PLAYBOOK.md。

2層構成:
  探索レイヤ (scout)  発掘 → 裏取り → 採点 → 日次レポート → /adopt でニッチ採用
  制作レイヤ (run)    採用ニッチで 台本/記事/動画 → /approve で投稿

サブコマンド:
  scout     発掘→裏取り→採点→日次レポート（探索レイヤ）
  run       収集→分類→安全性→Claudeで台本と記事→動画→レビュー投入→承認Issue作成
  review    レビューキューの一覧 / 承認 / 却下
  command   Issue コメント（/approve 等）を処理する（GitHub Actions から呼ぶ）
  publish   承認済みアイテムを TikTok へ投稿し、記事を書き出す
  report    週次レポートを出力
  revenue   発生した収益を記録
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from .config import ARTICLE_DIR, ROOT, Config, OUTPUT_DIR
from .collectors.twitter import TwitterCollector
from .models import Article, VideoScript
from .monetize.revenue import RevenueLog
from .processing.classifier import Classifier
from .processing.safety import SafetyChecker
from .processing.summarizer import Summarizer
from .publishers.github_issue import (
    Command,
    GitHubIssueSurface,
    parse_commands,
    render_approval_issue,
)
from .publishers.review_queue import ReviewQueue
from .publishers.tiktok import TikTokPublisher
from .video.builder import VideoBuilder

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
        self.issues = GitHubIssueSurface(self.config)
        self.revenue = RevenueLog()
        approval = self.config.section("approval")
        self.exclude_flagged = bool(approval.get("exclude_flagged_from_bulk", True))
        self.max_items_per_issue = int(approval.get("max_items_per_issue", 5))

    # ------------------------------------------------------------------
    def run(self, limit: int | None = None, use_sample: bool | None = None,
            open_issue: bool = False) -> list[str]:
        """収集から承認キュー投入まで。生成した item_id のリストを返す。"""
        limit = limit if limit is not None else self.max_items_per_issue

        collected = self.collector.collect(use_sample=use_sample)
        topics = self.classifier.build_topics(collected)
        topics = self.safety.filter_topics(topics)
        topics = self._apply_item_caps(topics)[:limit]

        if not self.summarizer.llm.available:
            logger.warning("LLM の API キーが未設定のため、テンプレ生成で動作します"
                           "（provider=%s）。文章の品質は上がりません。",
                           getattr(self.summarizer.llm, "provider", "?"))

        item_ids: list[str] = []
        cards: list[tuple] = []
        for topic in topics:
            script = self.summarizer.build_script(topic)
            article = self.summarizer.build_article(topic, script)

            item_id = f"{topic.category}-{topic.tweets[0].id}"
            video_path = self.video.build(script, OUTPUT_DIR / f"{item_id}.mp4")
            item = self.queue.enqueue(item_id, script, video_path,
                                      topic.safety_flags, category=topic.category,
                                      article=article)
            item_ids.append(item_id)
            cards.append((item, article.to_dict()))

        if open_issue:
            self._open_approval_issue(cards)

        logger.info("run 完了: %d 件をレビューキューに投入", len(item_ids))
        return item_ids

    @staticmethod
    def _apply_item_caps(topics: list) -> list:
        """投資レベルごとの本数上限を適用する（src/scout/commitment.py）。

        CHEAP_TEST のニッチから大量に作ってしまうと「小さく試す」が成立しない。
        上限のないカテゴリ（既定のニッチ）はそのまま通す。
        """
        try:
            from .scout.niches import NicheRegistry

            caps = NicheRegistry().item_caps()
        except Exception as exc:
            logger.debug("本数上限の読み込みをスキップしました: %s", exc)
            return topics
        if not caps:
            return topics

        used: dict[str, int] = {}
        kept = []
        for topic in topics:
            cap = caps.get(topic.category)
            if cap is not None:
                if used.get(topic.category, 0) >= cap:
                    continue
                used[topic.category] = used.get(topic.category, 0) + 1
            kept.append(topic)
        dropped = len(topics) - len(kept)
        if dropped:
            logger.info("投資レベルの上限により %d 件を見送りました: %s", dropped, used)
        return kept

    def _open_approval_issue(self, cards: list[tuple]) -> None:
        from datetime import date

        title = f"承認キュー {date.today().isoformat()}（{len(cards)}件）"
        body = render_approval_issue(cards)
        self.issues.create_issue(title, body)

    # ------------------------------------------------------------------
    def handle_comment(self, comment_body: str, issue_number: int | None = None) -> str:
        """Issue コメントのコマンドを処理し、返信用の Markdown を返す。"""
        commands = parse_commands(comment_body)
        if not commands:
            return ""

        replies: list[str] = []
        for cmd in commands:
            replies.append(self._run_command(cmd))

        reply = "\n".join(r for r in replies if r)
        if reply and issue_number is not None:
            self.issues.comment(issue_number, reply)
        return reply

    def _run_command(self, cmd: Command) -> str:
        if cmd.action == "status":
            return self._render_status()

        # 探索レイヤのコマンド。scout は重い import を持つので遅延ロードする。
        if cmd.action in ("adopt", "test", "scale", "drop", "metrics"):
            from .scout import ScoutPipeline
            from .scout.commitment import CHEAP_TEST, SCALE

            scout = ScoutPipeline(self.config)
            if cmd.action == "adopt":
                return scout.adopt(cmd.target)
            if cmd.action == "test":
                return scout.adopt(cmd.target, level=CHEAP_TEST)
            if cmd.action == "scale":
                return scout.adopt(cmd.target, level=SCALE)
            if cmd.action == "drop":
                return scout.drop(cmd.target)
            return scout.record_metrics(cmd.target, _parse_metrics(cmd.note))

        if cmd.action == "revenue":
            try:
                amount = int(float(cmd.target))
            except ValueError:
                return f"⚠️ 金額を数値で指定してください: `/revenue 3200 A8 案件名`（受け取った値: `{cmd.target}`）"
            source, _, note = cmd.note.partition(" ")
            self.revenue.log_revenue(amount, source or "unknown", note.strip())
            return f"✅ 収益 {amount:,}円 を記録しました（source={source or 'unknown'}）"

        if cmd.action == "approve" and cmd.target.lower() == "all":
            approved, skipped = self.queue.approve_all(self.exclude_flagged)
            for item_id in approved:
                self._log_status(item_id, "approved")
                approved_item = self.queue.get(item_id)
                self._log_attention("approve", approved_item.category if approved_item else "")
            lines = [f"✅ {len(approved)}件を承認しました。"]
            if approved:
                lines.append("　" + ", ".join(f"`{i}`" for i in approved))
            if skipped:
                lines.append(f"⚠️ safety_flags 付きの {len(skipped)}件は一括承認から除外しました。"
                             "個別に確認してください:")
                lines.append("　" + ", ".join(f"`{i}`" for i in skipped))
            return "\n".join(lines)

        item = self.queue.get(cmd.target)
        if item is None:
            return f"⚠️ `{cmd.target}` が見つかりません。`/status` でキューを確認してください。"

        if cmd.action == "approve":
            self.queue.approve(cmd.target)
            self._log_status(cmd.target, "approved")
            self._log_attention("approve", item.category)
            return f"✅ `{cmd.target}` を承認しました。次の publish で投稿されます。"

        self.queue.reject(cmd.target, cmd.note)
        self._log_status(cmd.target, "rejected")
        self._log_attention("reject", item.category)
        reason = f"（理由: {cmd.note}）" if cmd.note else ""
        return f"🚫 `{cmd.target}` を却下しました{reason}"

    def _render_status(self) -> str:
        lines = ["## キュー状況", ""]
        for status in ("pending", "approved", "rejected", "published"):
            items = self.queue.list_items(status=status)
            lines.append(f"- **{status}**: {len(items)}件")
            for item in items[:10]:
                flag = " ⚠️" if item.flagged else ""
                lines.append(f"  - `{item.id}`{flag} {item.script.get('title', '')}")
        return "\n".join(lines)

    def _log_attention(self, action: str, niche_slug: str = "") -> None:
        """判断1回分の時間を台帳に記録する。

        最終的な目的関数「人間の判断1分あたりの期待収益」の分母は、推定ではなく
        実測できる唯一の項なので、承認のたびに数える。
        """
        try:
            from .scout.ledger import ExperimentLedger

            ExperimentLedger().record_attention(action, niche_slug)
        except Exception as exc:   # 台帳が無くても制作は止めない
            logger.debug("判断時間の記録をスキップしました: %s", exc)

    def _log_status(self, item_id: str, status: str) -> None:
        item = self.queue.get(item_id)
        if item is None:
            return
        self.revenue.log_post(
            item_id=item_id,
            category=item.category,
            channel="-",
            status=status,
            route=item.article.get("monetization_route", "なし"),
            title=item.script.get("title", ""),
        )

    # ------------------------------------------------------------------
    def publish_approved(self) -> list[dict]:
        """承認済みアイテムを投稿し、記事を書き出す。

        REVIEW_REQUIRED=false なら pending も対象になるが、既定では承認必須。
        """
        statuses = ["approved"] if self.config.review_required else ["approved", "pending"]
        results: list[dict] = []

        for status in statuses:
            for item in self.queue.list_items(status=status):
                script = VideoScript(**item.script)
                video_path = self._ensure_video(item.id, item.video_path, script)
                result = self.publisher.publish(video_path, script)

                article_path = ""
                if item.article:
                    article_path = str(self._write_article(item.id, Article(**item.article)))

                results.append({"id": item.id, "tiktok": result, "article": article_path})
                if not self.config.dry_run:
                    self.queue.set_status(item.id, "published")
                    self.revenue.log_post(
                        item_id=item.id, category=item.category, channel="tiktok+article",
                        status="published",
                        route=item.article.get("monetization_route", "なし"),
                        title=item.script.get("title", ""),
                    )

        logger.info("publish 完了: %d 件", len(results))
        return results

    def _ensure_video(self, item_id: str, video_path: str, script: VideoScript) -> Path:
        """動画ファイルが無ければ台本から作り直す。

        GitHub Actions のランナーは実行ごとに破棄されるため、生成ジョブと投稿ジョブは
        別のマシンで走る。リポジトリにコミットするのは台本 JSON（軽い）だけにして、
        動画（重い）は投稿時に台本から再生成する。
        """
        path = Path(video_path) if video_path else OUTPUT_DIR / f"{item_id}.mp4"
        if not path.is_absolute():
            path = ROOT / path        # 保存はリポジトリ相対（review_queue._relative）
        if path.exists():
            return path
        logger.info("動画が見つかりません（%s）。台本から再生成します。", path)
        return self.video.build(script, OUTPUT_DIR / f"{item_id}.mp4")

    @staticmethod
    def _write_article(item_id: str, article: Article) -> Path:
        """記事を Markdown として書き出す。note / ブログへはここから貼る。"""
        ARTICLE_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTICLE_DIR / f"{item_id}.md"
        path.write_text(f"# {article.title}\n\n{article.body_markdown}\n", encoding="utf-8")
        logger.info("記事を書き出しました: %s", path)
        return path


# ---------------------------------------------------------------------------
def _cmd_run(args) -> None:
    Pipeline().run(limit=args.limit, use_sample=args.sample, open_issue=args.open_issue)


# 位置指定で書いたときの解釈順。個数で意味が決まるので曖昧にならない。
POSITIONAL_METRICS = {
    1: ("revenue",),
    2: ("views", "revenue"),
    3: ("views", "clicks", "revenue"),
    4: ("views", "clicks", "conversions", "revenue"),
}


def _parse_metrics(text: str) -> dict[str, int]:
    """実績の入力をパースする。スマホで打てる短さを優先している。

      /m xxx 3200                       → revenue だけ
      /m xxx 6000 3200                  → views, revenue
      /m xxx 6000 45 1 3200             → views, clicks, conversions, revenue
      /m xxx views=6000 revenue=3200    → 名前付き（順不同）

    桁区切りのカンマは落とす。名前付きと位置指定は混在してもよい（名前付きが優先）。
    """
    text = re.sub(r"(?<=\d),(?=\d)", "", text or "")
    named: dict[str, int] = {}
    positional: list[int] = []

    for token in text.replace(",", " ").split():
        key, sep, raw = token.partition("=")
        if sep:
            try:
                named[key.strip().lower()] = int(float(raw))
            except ValueError:
                logger.warning("数値として読めない値を無視しました: %s", token)
            continue
        try:
            positional.append(int(float(token)))
        except ValueError:
            logger.warning("数値として読めない値を無視しました: %s", token)

    values = dict(zip(POSITIONAL_METRICS.get(len(positional), ()), positional))
    if positional and len(positional) not in POSITIONAL_METRICS:
        logger.warning("位置指定は1〜4個までです（%d個を無視）。名前付きで指定してください。",
                       len(positional))
    values.update(named)          # 名前付きが位置指定に勝つ
    return values


def _cmd_scout(args) -> None:
    from .scout import ScoutPipeline

    _, report = ScoutPipeline().run(use_sample=args.sample, open_issue=args.open_issue)
    print(report)


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
            route = it.article.get("monetization_route", "なし")
            print(f"[{it.status}] {it.id}  flags={flags}  route={route}")
            print(f"    title: {it.script.get('title')}")
            print(f"    video: {it.video_path}")


def _cmd_command(args) -> None:
    body = args.body
    if not body and args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    reply = Pipeline().handle_comment(body or "", args.issue)
    print(reply or "（処理対象のコマンドはありませんでした）")


def _cmd_publish(args) -> None:
    Pipeline().publish_approved()


def _cmd_remind(args) -> None:
    """実績が未更新の採用ニッチだけをリマインダー Issue に出す。

    入力を促すが、入力しなくても運用は止まらない（UNKNOWN として記録される）。
    """
    from datetime import date

    from .publishers.github_issue import GitHubIssueSurface
    from .scout import ScoutPipeline

    config = Config.load()
    body = ScoutPipeline(config).render_metrics_reminder(days=args.days)
    if not body:
        print("未更新の採用ニッチはありません。")
        return

    print(body)
    if args.open_issue:
        surface = GitHubIssueSurface(config)
        surface.label = config.section("scout").get("label", "scout-report")
        surface.create_issue(f"実績の入力 {date.today().isoformat()}", body)


def _cmd_calibrate(args) -> None:
    """予測 vs 実績の対応表を出す。配点の見直しはこの表を見てから行う。"""
    from .scout.ledger import ExperimentLedger

    ledger = ExperimentLedger()
    table = ledger.calibration_table()
    if not table:
        print("予測と実績が対応した行がまだありません。"
              "`/adopt` で採用し、`/metrics` で実績を記録してください。")
        return
    keys = list(table[0].keys())
    print(" | ".join(keys))
    print("-|-".join("-" * len(k) for k in keys))
    for row in table:
        print(" | ".join(str(row[k]) for k in keys))


def _cmd_report(args) -> None:
    from .scout.ledger import ExperimentLedger

    report = RevenueLog().render_report(days=args.days)
    report = f"{report}\n\n{ExperimentLedger().render_report()}"
    print(report)
    if args.issue_title:
        GitHubIssueSurface(Config.load()).create_issue(args.issue_title, report)


def _cmd_revenue(args) -> None:
    RevenueLog().log_revenue(args.amount, args.source, args.note)
    print(f"記録しました: {args.amount:,}円 / {args.source}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline", description="スマホ承認型 AI 収益パイプライン"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scout = sub.add_parser("scout", help="発掘〜裏取り〜採点〜日次レポート")
    p_scout.add_argument("--sample", action="store_true", default=None,
                         help="サンプル候補で実行（未指定なら発掘元の有無で自動判定）")
    p_scout.add_argument("--open-issue", action="store_true", help="レポート Issue を作成する")
    p_scout.set_defaults(func=_cmd_scout)

    p_run = sub.add_parser("run", help="収集〜台本/記事/動画生成〜承認キュー投入")
    p_run.add_argument("--limit", type=int, default=None)
    # default=None が要点。store_true の既定 False を渡すと「トークンが無ければ
    # サンプルに落とす」自動判定（collectors/twitter.py）が働かず、空トークンで
    # X API を叩いて 401 で落ちる。
    p_run.add_argument("--sample", action="store_true", default=None,
                       help="サンプルデータで実行（未指定ならトークン有無で自動判定）")
    p_run.add_argument("--open-issue", action="store_true", help="承認 Issue を作成する")
    p_run.set_defaults(func=_cmd_run)

    p_rev = sub.add_parser("review", help="レビューキュー操作")
    p_rev.add_argument("--list", dest="_list", action="store_true")
    p_rev.add_argument("--status", default=None, help="pending/approved/rejected で絞り込み")
    p_rev.add_argument("--approve", metavar="ITEM_ID")
    p_rev.add_argument("--reject", metavar="ITEM_ID")
    p_rev.set_defaults(func=_cmd_review)

    p_cmd = sub.add_parser("command", help="Issue コメントのコマンドを処理")
    p_cmd.add_argument("--body", default="", help="コメント本文")
    p_cmd.add_argument("--body-file", default="", help="コメント本文を含むファイル")
    p_cmd.add_argument("--issue", type=int, default=None, help="返信先 Issue 番号")
    p_cmd.set_defaults(func=_cmd_command)

    p_pub = sub.add_parser("publish", help="承認済みを投稿し記事を書き出す")
    p_pub.add_argument("--approved", action="store_true")
    p_pub.set_defaults(func=_cmd_publish)

    p_rep = sub.add_parser("report", help="週次レポートを出力")
    p_rep.add_argument("--days", type=int, default=7)
    p_rep.add_argument("--issue-title", default="", help="指定すると Issue として投稿する")
    p_rep.set_defaults(func=_cmd_report)

    p_rem = sub.add_parser("remind", help="実績が未更新の採用ニッチをリマインドする")
    p_rem.add_argument("--days", type=int, default=7)
    p_rem.add_argument("--open-issue", action="store_true")
    p_rem.set_defaults(func=_cmd_remind)

    p_cal = sub.add_parser("calibrate", help="予測 vs 実績の対応表を出す")
    p_cal.set_defaults(func=_cmd_calibrate)

    p_money = sub.add_parser("revenue", help="発生した収益を記録")
    p_money.add_argument("--amount", type=int, required=True, help="金額（円）")
    p_money.add_argument("--source", required=True, help="ASP名など")
    p_money.add_argument("--note", default="")
    p_money.set_defaults(func=_cmd_revenue)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
