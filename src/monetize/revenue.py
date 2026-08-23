"""投稿ログと収益ログ。

自動化の失敗パターンは「回っているつもりで何も生んでいない」状態が続くこと。
週次レポート（.github/workflows/weekly-report.yml）でこのログを Issue に出し、
「今週の投稿数 / 承認率 / 収益」が見えるようにする。数字が動かない週が2回続いたら
ニッチか CTA を見直す、という判断ができる形にしている。

収益額は各アフィリ ASP の管理画面からしか取れないので、`log_revenue` で手入力する
（スマホから `/revenue 3200 A8 確定申告ソフト` のようにコメントする運用でも良い）。
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR

logger = logging.getLogger(__name__)

POSTS_CSV = DATA_DIR / "posts.csv"
REVENUE_CSV = DATA_DIR / "revenue.csv"

POST_FIELDS = ["timestamp", "item_id", "category", "channel", "status", "route", "title"]
REVENUE_FIELDS = ["timestamp", "amount_jpy", "source", "note"]


@dataclass
class WeeklySummary:
    posted: int
    approved: int
    rejected: int
    revenue_jpy: int
    by_category: dict[str, int]
    routeless: int

    @property
    def approval_rate(self) -> float:
        total = self.approved + self.rejected
        return (self.approved / total * 100) if total else 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RevenueLog:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.posts_csv = data_dir / "posts.csv"
        self.revenue_csv = data_dir / "revenue.csv"
        data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def log_post(self, item_id: str, category: str, channel: str, status: str,
                 route: str, title: str) -> None:
        """投稿（または承認/却下）を1行追記する。"""
        self._append(self.posts_csv, POST_FIELDS, {
            "timestamp": _now(), "item_id": item_id, "category": category,
            "channel": channel, "status": status, "route": route, "title": title,
        })

    def log_revenue(self, amount_jpy: int, source: str, note: str = "") -> None:
        """発生した収益を1行追記する（ASP の管理画面から手入力）。"""
        self._append(self.revenue_csv, REVENUE_FIELDS, {
            "timestamp": _now(), "amount_jpy": amount_jpy, "source": source, "note": note,
        })

    # ------------------------------------------------------------------
    def summarize(self, days: int = 7) -> WeeklySummary:
        """直近 N 日の集計。"""
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        posted = approved = rejected = routeless = 0
        by_category: dict[str, int] = {}

        for row in self._read(self.posts_csv):
            if self._ts(row.get("timestamp", "")) < cutoff:
                continue
            status = row.get("status", "")
            if status == "published":
                posted += 1
                cat = row.get("category", "unknown")
                by_category[cat] = by_category.get(cat, 0) + 1
            elif status == "approved":
                approved += 1
            elif status == "rejected":
                rejected += 1
            if row.get("route", "") in ("", "なし"):
                routeless += 1

        revenue = 0
        for row in self._read(self.revenue_csv):
            if self._ts(row.get("timestamp", "")) < cutoff:
                continue
            try:
                revenue += int(float(row.get("amount_jpy", 0)))
            except ValueError:
                continue

        return WeeklySummary(posted=posted, approved=approved, rejected=rejected,
                             revenue_jpy=revenue, by_category=by_category,
                             routeless=routeless)

    def render_report(self, days: int = 7, adopted: int | None = None) -> str:
        """週次レポート（Markdown）。Issue にそのまま貼る。

        `adopted` は採用済みニッチ数。0 件のときに「承認が止まっている」と
        書くと誤診断になる（止まったのではなく、まだ始まっていない）ため区別する。
        """
        s = self.summarize(days)
        lines = [
            f"# 週次レポート（直近{days}日）",
            "",
            f"- 投稿: **{s.posted}件**",
            f"- 承認 {s.approved} / 却下 {s.rejected}（承認率 {s.approval_rate:.0f}%）",
            f"- 収益: **{s.revenue_jpy:,}円**",
        ]
        if s.by_category:
            breakdown = " / ".join(f"{k} {v}" for k, v in sorted(s.by_category.items()))
            lines.append(f"- カテゴリ別投稿: {breakdown}")
        if s.routeless:
            lines.append(f"- ⚠️ 換金経路なしの案件: {s.routeless}件（`AFF_*` Secrets を確認）")

        lines.extend(["", "## 判断", ""])
        if s.posted == 0 and adopted == 0:
            lines.append("- まだ採用したニッチがない。リサーチ結果 Issue で "
                         "`/test <id>` を1つ押すところから始める。")
        elif s.posted == 0:
            lines.append("- 投稿ゼロ。承認が止まっている。通勤中の承認を再開するか cron を確認する。")
        elif s.revenue_jpy == 0 and s.posted >= 10:
            lines.append("- 投稿は出ているが収益ゼロ。CTA の位置とニッチ選定を見直す"
                         "（docs/PLAYBOOK.md の 3 と 8）。")
        elif s.revenue_jpy > 0:
            lines.append("- 換金経路が機能している。伸びているカテゴリに投稿を寄せる。")
        if s.approval_rate and s.approval_rate < 50:
            lines.append("- 却下が多い。`llm.editorial_policy` を修正して生成品質を上げる。")

        lines.extend(["", "収益は `python -m src.pipeline revenue --amount <円> --source <ASP名>` で記録する。"])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    @staticmethod
    def _ts(value: str) -> float:
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _read(path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _append(path: Path, fields: list[str], row: dict) -> None:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
