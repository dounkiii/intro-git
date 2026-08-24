"""実行記録のテスト。

一番守りたいのは「success でも中身が壊れている回を見逃さない」こと。
これまでのバグ12件のうち、失敗として通知されたのは1件だけで、残りは
success のログを読んで見つけた。
"""
import pathlib

import pytest

from src.ops.runlog import MARKERS, RunLog, scan

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_成功でも異常マーカーがあれば要確認になる(tmp_path):
    """これが本題。これまでのバグ12件のうち失敗として通知されたのは1件だけで、
    残りは success のログを読んで見つけた。"""
    log = RunLog(tmp_path / "runs.jsonl")
    rec = log.record("daily-scout", "success", ts="2026-08-24T21:00:00+00:00",
                     log_text="⚠️ **未採点** — 数値を判断に使わないでください")

    assert rec.status == "success"
    assert rec.needs_attention
    assert "unscored" in rec.anomalies


def test_異常が無い成功は要確認にならない(tmp_path):
    log = RunLog(tmp_path / "runs.jsonl")
    rec = log.record("daily-scout", "success", ts="2026-08-24T21:00:00+00:00",
                     log_text="INFO 探索完了: 3件")

    assert not rec.needs_attention
    assert rec.anomalies == []


def test_失敗は異常マーカーが無くても要確認(tmp_path):
    log = RunLog(tmp_path / "runs.jsonl")
    rec = log.record("daily-generate", "failure", ts="2026-08-24T21:00:00+00:00",
                     log_text="")

    assert rec.needs_attention


@pytest.mark.parametrize("key,sample", [
    ("unscored", "⚠️ **未採点** — LLM の API キーが未設定"),
    ("no_route", "WARNING category=tax に換金経路がありません。AFF_* の環境変数を"),
    ("model_gone", "models/gemini-2.5-flash is no longer available to new users"),
    ("rate_limited", "HTTP 429 レート上限に達しました"),
    ("template_fallback", "LLM の API キーが未設定のため、テンプレ生成で動作します"),
    ("duration_over", "合計尺が 115.0秒で max_duration_sec=90 を超えています"),
    ("traceback", 'Traceback (most recent call last):\n  File "x.py"'),
])
def test_過去に起きた異常をログから拾える(key, sample):
    """マーカーは実際に起きたバグから採っている。推測で増やすと誤検知になる。"""
    keys, _ = scan(sample)

    assert key in keys, f"{key} を拾えていません: {sample!r}"


def test_マーカーには対処法が書かれている():
    """異常名だけ出しても、朝の点検が次に何をすればいいか分からない。"""
    for key, pattern, note in MARKERS:
        assert key and pattern and note.strip(), f"{key} の定義が不完全"


def test_要確認の回だけを新しい順に返す(tmp_path):
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "success", ts="1", log_text="ok")
    log.record("daily-scout", "failure", ts="2", log_text="")
    log.record("daily-generate", "success", ts="3", log_text="未採点")

    pending = log.pending()

    assert [p["ts"] for p in pending] == ["3", "2"]


def test_記録が無くてもレポートは落ちない(tmp_path):
    assert "まだありません" in RunLog(tmp_path / "runs.jsonl").render_report()


def test_レポートにログURLと対処法が出る(tmp_path):
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "success", ts="2026-08-24T21:00:00+00:00",
               log_text="換金経路がありません",
               run_url="https://github.com/o/r/actions/runs/1")

    report = log.render_report()

    assert "https://github.com/o/r/actions/runs/1" in report
    assert "AFF_*" in report


def test_失敗した回も記録がpushされる():
    """ジョブが落ちるとコミットステップは動かない。記録ステップを
    if: always() で独立させ、data/ops/ だけを push する必要がある。"""
    for name in ("daily-scout.yml", "daily-generate.yml"):
        text = (REPO / ".github/workflows" / name).read_text(encoding="utf-8")
        # 記録ステップが always() で動く
        record_at = text.index("実行結果を記録")
        tail = text[record_at:]
        assert "if: always()" in tail.split("- name:")[0], name
        # そのステップ自身が push する（後段のコミットに依存しない）
        step = tail.split("\n      - name:")[0]
        assert "git add -A data/ops/" in step, name
        assert "git push" in step, name


def test_記録はログをファイル経由で受け取る():
    """パイプの途中で成否が消えないよう pipefail を立てていること。"""
    for name in ("daily-scout.yml", "daily-generate.yml"):
        text = (REPO / ".github/workflows" / name).read_text(encoding="utf-8")

        assert "set -o pipefail" in text, name
        assert "tee /tmp/pipeline.log" in text, name
        assert "--log /tmp/pipeline.log" in text, name
