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
