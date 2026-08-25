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

    def pending(self, limit: int = 10) -> list[dict]:
        """要確認の回を新しい順に返す。毎朝の点検が最初に見るもの。"""
        flagged = [r for r in self.rows()
                   if r.get("status") != "success" or r.get("anomalies")]
        return flagged[-limit:][::-1]

    def render_report(self, limit: int = 10) -> str:
        """毎朝の点検が読む要約（Markdown）。"""
        flagged = self.pending(limit)
        if not flagged:
            rows = self.rows()
            return (f"要確認の実行はありません（記録 {len(rows)}件）。"
                    if rows else "実行の記録がまだありません。")

        lines = [f"# 要確認の実行 {len(flagged)}件", ""]
        for r in flagged:
            lines.append(f"## {r.get('workflow')} — {r.get('status')} "
                         f"（{r.get('ts')}）")
            if r.get("run_url"):
                lines.append(f"- ログ: {r['run_url']}")
            for note in r.get("notes") or []:
                lines.append(f"- ⚠️ {note}")
            lines.append("")
        return "\n".join(lines)
