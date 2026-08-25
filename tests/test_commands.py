"""Issue コメントコマンドのパースと一括承認の安全装置のテスト。"""
from __future__ import annotations

from src.models import VideoScript
from src.publishers.github_issue import parse_commands, render_approval_issue
from src.publishers.review_queue import ReviewQueue


def test_複数行のコマンドを全部拾う():
    commands = parse_commands(
        "おはようございます\n"
        "/approve tax-123\n"
        "/reject tax-456 個人名が入っている\n"
        "/status\n"
    )

    assert [(c.action, c.target, c.note) for c in commands] == [
        ("approve", "tax-123", ""),
        ("reject", "tax-456", "個人名が入っている"),
        ("status", "", ""),
    ]


def test_大文字や前後の空白を許容する():
    commands = parse_commands("  /APPROVE all  ")
    assert len(commands) == 1
    assert commands[0].action == "approve"
    assert commands[0].target == "all"


def test_引数のないコマンドは無視される():
    assert parse_commands("/approve") == []


def test_コマンドでない行は拾わない():
    assert parse_commands("approve tax-123\nhttps://example.com/approve x") == []


def test_収益コマンドをパースできる():
    (cmd,) = parse_commands("/revenue 3200 A8 確定申告ソフト")
    assert (cmd.action, cmd.target, cmd.note) == ("revenue", "3200", "A8 確定申告ソフト")


# ---------------------------------------------------------------------------
def _enqueue(queue: ReviewQueue, item_id: str, flags: list[str]) -> None:
    script = VideoScript(topic_category="tax", title=f"title-{item_id}",
                         slides=["a"], narration=["a"])
    queue.enqueue(item_id, script, video_path="/tmp/x.mp4", safety_flags=flags,
                  category="tax")


def test_一括承認はフラグ付きを除外する(tmp_path):
    queue = ReviewQueue(tmp_path)
    _enqueue(queue, "clean-1", [])
    _enqueue(queue, "flagged-1", ["unverified_claim"])

    approved, skipped = queue.approve_all(exclude_flagged=True)

    assert approved == ["clean-1"]
    assert skipped == ["flagged-1"]
    assert queue.get("flagged-1").status == "pending"


def test_除外を切れば全件承認される(tmp_path):
    queue = ReviewQueue(tmp_path)
    _enqueue(queue, "clean-1", [])
    _enqueue(queue, "flagged-1", ["unverified_claim"])

    approved, skipped = queue.approve_all(exclude_flagged=False)

    assert sorted(approved) == ["clean-1", "flagged-1"]
    assert skipped == []


def test_却下理由が保存される(tmp_path):
    queue = ReviewQueue(tmp_path)
    _enqueue(queue, "clean-1", [])

    queue.reject("clean-1", "制度の解釈が違う")

    item = queue.get("clean-1")
    assert item.status == "rejected"
    assert item.reject_reason == "制度の解釈が違う"


def test_承認Issueに確認すべき3点が出る(tmp_path):
    queue = ReviewQueue(tmp_path)
    _enqueue(queue, "tax-1", ["unverified_claim"])
    item = queue.get("tax-1")

    body = render_approval_issue([(item, {"monetization_route": "確定申告ソフト (AFF_X)",
                                          "body_markdown": "本文"})])

    assert "`tax-1`" in body
    assert "unverified_claim" in body
    assert "確定申告ソフト (AFF_X)" in body
    assert "/approve tax-1" in body


def test_換金経路なしは承認Issueで警告される(tmp_path):
    queue = ReviewQueue(tmp_path)
    _enqueue(queue, "tax-1", [])
    item = queue.get("tax-1")

    body = render_approval_issue([(item, {"monetization_route": "なし"})])

    assert "AFF_* Secrets を確認" in body


def test_動画パスはリポジトリ相対で保存される(tmp_path):
    """絶対パスを保存すると、Actions のランナーとローカルで値が変わり、
    実行するたびにコミット済みの状態ファイルが汚れて競合の種になる。"""
    from src.config import ROOT

    queue = ReviewQueue(tmp_path)
    script = VideoScript(topic_category="tax", title="t", slides=["a"], narration=["a"])

    item = queue.enqueue("tax-1", script,
                         video_path=ROOT / "data" / "output" / "tax-1.mp4",
                         safety_flags=[], category="tax")

    assert item.video_path == "data/output/tax-1.mp4"
    assert not item.video_path.startswith("/")


def test_リポジトリ外の絶対パスはそのまま保存される(tmp_path):
    """一時ディレクトリなどリポジトリ外を指す場合は相対化できないので触らない。"""
    queue = ReviewQueue(tmp_path)
    script = VideoScript(topic_category="tax", title="t", slides=["a"], narration=["a"])

    item = queue.enqueue("tax-2", script, video_path=tmp_path / "x.mp4",
                         safety_flags=[], category="tax")

    assert item.video_path.endswith("x.mp4")


def test_週次レポートは承認キューとは別のラベルを使う():
    """承認ワークフローは approval-queue ラベルで起動する。週次レポートに同じ
    ラベルを付けると、レポートへのコメントで承認処理が誤発火する。"""
    from src.config import Config

    approval = Config.load().section("approval")

    assert approval["label"] != approval["report_label"]


def test_承認ワークフローがレポートのラベルで起動しない():
    import pathlib

    workflow = pathlib.Path(".github/workflows/approve-command.yml").read_text(encoding="utf-8")
    from src.config import Config

    report_label = Config.load().section("approval")["report_label"]

    assert f"'{report_label}'" not in workflow


def test_承認Issueは実際に生成したプロバイダを出す(tmp_path):
    """Claude 以外で生成したものを「Claude」と表示すると、承認画面で品質を
    判断する材料が壊れる。実績を見るときに Claude 期と Gemini 期も混ざる。"""
    queue = ReviewQueue(tmp_path)
    script = VideoScript(topic_category="tax", title="t", slides=["a"],
                         narration=["a"], generated_by="gemini")
    queue.enqueue("tax-1", script, video_path="/tmp/x.mp4", safety_flags=[],
                  category="tax")
    item = queue.get("tax-1")

    body = render_approval_issue([(item, {"monetization_route": "なし"})])

    assert "gemini" in body
    assert "Claude" not in body


def test_テンプレ落ちは設定中のプロバイダのキーを名指しする(tmp_path):
    """プロバイダを差し替えたのに別のキーを案内すると、オーナーが直せない
    場所を確認しにいくことになる。"""
    queue = ReviewQueue(tmp_path)
    _enqueue(queue, "tax-1", [])
    item = queue.get("tax-1")

    body = render_approval_issue([(item, {"monetization_route": "なし"})],
                                 api_key_env="GEMINI_API_KEY")

    assert "GEMINI_API_KEY 未設定" in body
    assert "ANTHROPIC_API_KEY" not in body


def test_全プロバイダがキーの環境変数名を持つ():
    """承認 Issue がテンプレ落ちの原因を名指しするために必要。プロバイダを
    足したときに漏れると、案内が「LLM の API キー未設定」に退化する。"""
    from src.llm.claude import ClaudeClient
    from src.llm.gemini import GeminiClient

    for client in (ClaudeClient, GeminiClient):
        assert client.api_key_env
        assert client.provider


def test_状態をコミットするワークフローは_push_前に_pull_する():
    """pull を省くと、他のワークフローや手元からの push と競合したときに
    push が拒否され、その回の探索結果や承認結果が失われる。

    `--autostash` が要る理由（2026-08-24 に実際に起きた）: 記録ステップは
    data/ops/ だけをコミットするので、パイプラインが書いた data/scout/ などは
    未ステージのまま残る。その状態で pull --rebase すると
    "cannot pull with rebase: You have unstaged changes" で落ち、
    **成功していた探索ジョブごと failure になって結果が失われた。**
    """
    import pathlib

    for name in ("daily-scout.yml", "daily-generate.yml", "approve-command.yml"):
        text = pathlib.Path(".github/workflows", name).read_text(encoding="utf-8")
        if "git push" not in text:
            continue
        pull = text.index("git pull --rebase")
        push = text.index("git push")
        assert pull < push, name
        # 未ステージの生成物があっても落ちないこと
        assert "git pull --rebase --autostash origin" in text, name
        # 衝突は握り潰さない（|| true を付けると壊れた状態を push しうる）
        assert "git pull --rebase --autostash origin \"${{ github.ref_name }}\" || true" \
            not in text, name


def test_台本の指示に尺の上下限が入る():
    """下限だけ伝えると LLM は上限を知らないまま長く書き、builder は警告する
    だけで切り詰めないので、config の max_duration_sec が効かなくなる。"""
    from src.config import Config
    from src.models import Tweet, Topic
    from src.processing.summarizer import Summarizer

    config = Config.load()
    video = config.section("video")
    summarizer = Summarizer(config)
    topic = Topic(category="tax", headline="t", score=1.0, tweets=[
        Tweet(id="1", text="本文", author="a", url="https://example.com",
              created_at="", likes=1, retweets=0, replies=0)])

    captured: dict = {}
    summarizer.llm.generate_json = (
        lambda system, prompt, schema: captured.setdefault("prompt", prompt))
    summarizer._script_via_claude(topic)

    assert str(video["min_duration_sec"]) in captured["prompt"]
    assert str(video["max_duration_sec"]) in captured["prompt"]
