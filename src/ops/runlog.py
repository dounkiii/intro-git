"""スケジュール実行の結果をリポジトリに残す。

**なぜ必要か。** ジョブが失敗しても記録はオーナーのメールにしか残らず、
Actions のログは API 経由でしか読めない。このセッション環境では
`api.github.com` がプロキシで止まるため、git 以外の経路が無い場面がある
（毎朝の自動点検セッションがその状況）。そこで実行結果を
`data/ops/runs.jsonl` に追記し、**git だけで読める**ようにする。

**success でも中身が壊れていることが何度もあった**ので、成否だけでなくログ中の
異常マーカーも記録する。マーカーは実際に起きたバグから採っている
（`docs/RESEARCH_SYSTEM.md` の「運用フェーズで直した実装バグ（台帳）」）。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import DATA_DIR

logger = logging.getLogger(__name__)

OPS_DIR = DATA_DIR / "ops"
RUNS_PATH = OPS_DIR / "runs.jsonl"

# ログ中の異常マーカー。(キー, 正規表現, 説明) の並び。
# 過去に実際に起きたものだけを入れる。推測で増やすと誤検知で狼少年になる。
MARKERS: list[tuple[str, str, str]] = [
    ("unscored", r"未採点",
     "LLM の採点が失敗している。数値を判断に使わないこと"),
    ("no_route", r"換金経路がありません",
     "AFF_* が届いていない。ワークフローの env と Secrets を確認"),
    ("model_gone", r"no longer available|models/[\w.\-]+ is not found",
     "モデル名が無効。config の llm.gemini_model を後継名に直す"),
    ("rate_limited", r"レート上限|429",
     "無料枠の上限。scout.research_limit を下げるか min_interval_seconds を上げる"),
    ("template_fallback", r"テンプレ生成で動作|テンプレート生成にフォールバック",
     "LLM が使えていない。API キーの Secret を確認"),
    ("duration_over", r"max_duration_sec=\d+ を超え",
     "尺が上限を超えている。台本側に上限が伝わっていない"),
    ("traceback", r"Traceback \(most recent call last\)",
     "未捕捉の例外。実装バグ"),
    # 2026-08-24: ワークフローの行継続を壊してしまい argparse が引数を拒否した。
    # status=failure は記録できたが anomalies が空で、原因の手がかりが残らなかった。
    ("cli_error", r"^usage: pipeline|pipeline: error:",
     "コマンドの呼び方が壊れている。ワークフローの引数と行継続を確認"),
]


# 動いていることを期待するワークフローと、記録が途絶えたと見なす時間（時）。
#
# **なぜ必要か。** ここまでの点検は「記録された回」しか見ていなかった。
# 1回も動かなければ行が無く、`pending()` は空を返し、レポートは静かなままになる。
# 実際に朝の点検（morning-check）は3回続けて記録を残さなかったのに、
# リポジトリ上は異常なしに見えていた。**沈黙は成功と区別できない。**
#
# しきい値が24時間ではなく36時間なのは、GitHub の schedule が大きく遅れるため。
# 実測で 20:00 UTC 予定の回が翌 04:03 に動いている（約8時間）。24時間で切ると
# 正常に動いた翌日に誤検知する。
EXPECTED_WORKFLOWS: dict[str, int] = {
    "daily-scout": 36,
    "daily-generate": 36,
    "morning-check": 36,
}


@dataclass
class RunRecord:
    """1回の実行の記録。"""

    workflow: str
    status: str = ""          # success / failure / cancelled
    ts: str = ""
    run_url: str = ""
    anomalies: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        """人（または朝の点検）が見るべき回か。"""
        return self.status != "success" or bool(self.anomalies)

    def to_dict(self) -> dict:
        return asdict(self)


def scan(log_text: str) -> tuple[list[str], list[str]]:
    """ログから異常マーカーを拾う。(キー一覧, 説明一覧) を返す。"""
    keys: list[str] = []
    notes: list[str] = []
    for key, pattern, note in MARKERS:
        if re.search(pattern, log_text, re.MULTILINE):
            keys.append(key)
            notes.append(f"{key}: {note}")
    return keys, notes


class RunLog:
    def __init__(self, path: Path = RUNS_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, workflow: str, status: str, ts: str,
               log_text: str = "", run_url: str = "") -> RunRecord:
        """実行結果を追記する。`ts` は呼び出し側から渡す（テストを固定できるように）。"""
        anomalies, notes = scan(log_text)
        rec = RunRecord(workflow=workflow, status=status or "unknown", ts=ts,
                        run_url=run_url, anomalies=anomalies, notes=notes)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        if rec.needs_attention:
            logger.warning("要確認の実行: %s status=%s anomalies=%s",
                           workflow, rec.status, anomalies or "なし")
        return rec

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def latest_per_workflow(self) -> dict[str, dict]:
        """ワークフローごとの最新の記録。"""
        latest: dict[str, dict] = {}
        for r in self.rows():
            latest[r.get("workflow", "?")] = r
        return latest

    def pending(self, limit: int = 10) -> list[dict]:
        """いま壊れているワークフローだけを返す。毎朝の点検が最初に見るもの。

        **過去の失敗は、その後に成功していれば出さない。** 直した失敗を毎朝
        蒸し返すと、点検が解決済みの問題を調べ直すことになり、失敗の履歴が
        増えるほど無駄が増える。「このワークフローは今どうか」を返す。

        時間窓で切らないのは、点検が1日飛んでも壊れたままなら報告してほしいため。
        """
        flagged = [r for r in self.latest_per_workflow().values()
                   if r.get("status") != "success" or r.get("anomalies")]
        flagged.sort(key=lambda r: r.get("ts", ""))
        return flagged[-limit:][::-1]

    def stale(self, now: datetime | None = None) -> list[tuple[str, str]]:
        """記録が途絶えているワークフローを返す。(名前, 最後の記録) の並び。

        **`pending()` では拾えない異常。** あちらは記録された回を見るので、
        「1回も動かなかった」「動いたが記録を残さずに終わった」は行が無く、
        何も報告されない。実際に朝の点検が3回続けて無記録だったのに、
        レポートは「要確認の実行はありません」を出していた。
        """
        now = now or datetime.now(timezone.utc)
        latest = self.latest_per_workflow()
        out: list[tuple[str, str]] = []
        for workflow, hours in EXPECTED_WORKFLOWS.items():
            row = latest.get(workflow)
            if row is None:
                out.append((workflow, "記録なし"))
                continue
            ts = _parse_ts(row.get("ts", ""))
            if ts is None:
                # 記録はあるが時刻が読めない。判定不能なので黙って落とさない
                out.append((workflow, f"時刻を読めません（{row.get('ts')!r}）"))
                continue
            if (now - ts).total_seconds() > hours * 3600:
                out.append((workflow, row.get("ts", "")))
        return out

    def recovered(self) -> list[dict]:
        """直近で失敗したが、その後の実行で回復したもの。

        対処は不要だが、繰り返すなら不安定さの手がかりになるので出す。
        """
        out = []
        for workflow, latest in self.latest_per_workflow().items():
            if latest.get("status") != "success" or latest.get("anomalies"):
                continue
            history = [r for r in self.rows() if r.get("workflow") == workflow]
            if any(r.get("status") != "success" or r.get("anomalies")
                   for r in history[:-1]):
                out.append(latest)
        return out

    def render_report(self, limit: int = 10,
                      now: datetime | None = None) -> str:
        """毎朝の点検が読む要約（Markdown）。

        **失敗した回だけでなく、途絶えたワークフローも出す。** 記録が無いことは
        レポート上で成功と見分けがつかず、実際にそれで3回見落としている。
        """
        rows = self.rows()
        if not rows:
            return "実行の記録がまだありません。"

        flagged = self.pending(limit)
        stale = self.stale(now)
        lines: list[str] = []

        if stale:
            lines.append(f"# 記録が途絶えています {len(stale)}件")
            lines.append("")
            for workflow, last in stale:
                lines.append(f"## {workflow} — 最後の記録: {last}")
                lines.append("- ⚠️ 動いていないか、動いたが記録を残さずに"
                             "終わっている。ワークフローの schedule と、"
                             "記録ステップの push が通っているかを確認")
                lines.append("")

        if flagged:
            lines.append(f"# 要確認の実行 {len(flagged)}件")
            lines.append("")
            for r in flagged:
                lines.append(f"## {r.get('workflow')} — {r.get('status')} "
                             f"（{r.get('ts')}）")
                if r.get("run_url"):
                    lines.append(f"- ログ: {r['run_url']}")
                for note in r.get("notes") or []:
                    lines.append(f"- ⚠️ {note}")
                lines.append("")

        if not flagged:
            lines.append(f"要確認の実行はありません（記録 {len(rows)}件）。")
            for r in self.recovered():
                lines.append(f"- {r.get('workflow')}: 過去に失敗があるが"
                             f"直近は成功（{r.get('ts')}）。対処不要")

        return "\n".join(lines)


def _parse_ts(value: str) -> datetime | None:
    """記録の時刻を読む。読めなければ None（推測で埋めない）。

    テストは `ts="1"` のような固定値を使うので、読めない値は普通に来る。
    それを「古い」と決めつけると、テスト用の記録が毎回途絶扱いになる。
    """
    try:
        ts = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
