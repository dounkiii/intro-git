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


def test_コマンドの呼び方が壊れた回を拾える():
    """2026-08-24: ワークフローの行継続を壊し argparse が引数を拒否した。
    status=failure は記録できたが anomalies が空で手がかりが残らなかった。"""
    log = """usage: pipeline [-h]
                {scout,run,review,command,publish,report,remind,calibrate}
                ...
pipeline: error: unrecognized arguments:  2"""

    keys, notes = scan(log)

    assert "cli_error" in keys
    assert any("行継続" in n for n in notes)


def test_失敗した回に手がかりが残る():
    """失敗を記録できても anomalies が空だと、朝の点検が次に何を見るか分からない。"""
    from src.ops.runlog import MARKERS

    covered = {k for k, _, _ in MARKERS}

    # 実際に起きた失敗の型は最低限カバーしていること
    assert {"traceback", "cli_error"} <= covered


def test_直した失敗を毎朝蒸し返さない(tmp_path):
    """過去の失敗をそのまま出し続けると、点検が解決済みの問題を調べ直す。
    失敗の履歴が増えるほど無駄が増える。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-generate", "failure", ts="2026-08-24T21:16:00+00:00")
    log.record("daily-generate", "success", ts="2026-08-25T05:00:00+00:00")

    assert log.pending() == []
    report = log.render_report()
    assert "要確認の実行はありません" in report
    # ただし「回復した」ことは分かるようにする（繰り返すなら不安定さの手がかり）
    assert "直近は成功" in report


def test_まだ壊れているものは日が経っても出す(tmp_path):
    """時間窓で切ると、点検が1日飛んだときに壊れたままの回を見落とす。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "success", ts="2026-08-20T20:00:00+00:00")
    log.record("daily-generate", "failure", ts="2026-08-20T21:00:00+00:00")

    pending = log.pending()

    assert [p["workflow"] for p in pending] == ["daily-generate"]


def test_ワークフローごとに最新だけを見る(tmp_path):
    """片方が直っても、もう片方が壊れていれば出す。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "failure", ts="1")
    log.record("daily-generate", "failure", ts="2")
    log.record("daily-scout", "success", ts="3")

    assert [p["workflow"] for p in log.pending()] == ["daily-generate"]


def test_成功でも異常が残っていれば出し続ける(tmp_path):
    """status だけ見ると、success の裏で壊れている回を取りこぼす。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "failure", ts="1")
    log.record("daily-scout", "success", ts="2", log_text="未採点")

    assert [p["workflow"] for p in log.pending()] == ["daily-scout"]


def test_数秒の尺超過は要確認にしない():
    """2026-08-25 の実測は 91.3秒 / 上限 90秒 の 1.3秒超過だった。
    これを毎朝拾うと誤検知で狼少年になる。builder 側が許容範囲を
    INFO に落とすので、マーカーは拾わないこと。"""
    keys, _ = scan("INFO src.video.builder: 合計尺 91.3秒"
                   "（max_duration_sec=90 を 1.3秒 超過）。許容範囲なので対処不要")

    assert "duration_over" not in keys


def test_大きな尺超過は要確認にする():
    """修正前の実測は 115.0秒 / 上限 90秒 だった。これは拾う。"""
    keys, _ = scan("WARNING src.video.builder: 合計尺が 115.0秒で "
                   "max_duration_sec=90 を超えています。")

    assert "duration_over" in keys


# --------------------------------------------------------------------------
# 記録が途絶えたワークフローを拾う
#
# ここまでの点検は「記録された回」しか見ていなかった。1回も動かなければ行が
# 無く、pending() は空を返し、レポートは静かなままだった。朝の点検自身が
# 2026-08-24 / 08-25 / 08-30 と3回無記録だったのに異常なしに見えていたのはこれ。
# --------------------------------------------------------------------------

def _now():
    from datetime import datetime, timezone
    return datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def test_一度も記録が無いワークフローを拾う(tmp_path):
    """これが本題。動かなかったワークフローには行が無いので、
    行を見ているだけでは永久に気づけない。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "success", ts="2026-08-30T02:00:00+00:00")

    missing = dict(log.stale(now=_now()))

    assert missing["morning-check"] == "記録なし"
    assert "daily-scout" not in missing


def test_点検が黙って落ちた夜を検知する(tmp_path):
    """朝の点検は発火して success で終わったのに記録を残さなかった。
    Routine 側は成功に見えるので、気づけるのはリポジトリの中だけ。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("morning-check", "success", ts="2026-08-27T22:20:00+00:00")

    missing = dict(log.stale(now=_now()))

    assert missing["morning-check"] == "2026-08-27T22:20:00+00:00"


def test_cronの遅れを途絶と誤検知しない(tmp_path):
    """GitHub の schedule は大きく遅れる。実測で 20:00 UTC 予定の回が
    翌 04:03 に動いていた（約8時間）。24時間で切ると誤検知になる。"""
    log = RunLog(tmp_path / "runs.jsonl")
    for w in ("daily-scout", "daily-generate", "morning-check"):
        # 前日の予定から8時間ずれて動いた回
        log.record(w, "success", ts="2026-08-29T04:03:00+00:00")

    assert log.stale(now=_now()) == []


def test_読めない時刻を古い記録と決めつけない(tmp_path):
    """時刻が壊れているのは「途絶えた」とは違う異常。混ぜると原因が分からない。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "success", ts="こわれた値")

    reason = dict(log.stale(now=_now()))["daily-scout"]

    assert "読めません" in reason


def test_途絶はレポートに出る(tmp_path):
    """pending が0件でも「静かな夜」と「異常なし」を混同しないこと。"""
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("daily-scout", "success", ts="2026-08-30T02:00:00+00:00")

    report = log.render_report(now=_now())

    assert "記録が途絶えています" in report
    assert "morning-check" in report


def test_期待するワークフローに点検自身が入っている():
    """見張り番を見張る対象から外すと、黙って落ちても誰も気づかない。"""
    from src.ops.runlog import EXPECTED_WORKFLOWS

    assert "morning-check" in EXPECTED_WORKFLOWS
    assert {"daily-scout", "daily-generate"} <= set(EXPECTED_WORKFLOWS)


def test_実データのガードは除外に理由を求める():
    """conftest.py は pytest がテストとして収集しないので、ここで検証する。
    理由なしの除外を許すと、除外リストが守り漏れの隠し場所になる。"""
    from tests.conftest import EXEMPT

    assert EXEMPT, "除外が空なら理由の検証も要らないはずで、書き間違いの可能性"
    for name, reason in EXEMPT.items():
        assert reason.strip(), f"{name} の除外理由が空です"
