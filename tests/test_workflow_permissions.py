"""ワークフローの権限の契約テスト。

2026-08-31: Pages のワークフローに `permissions: contents: read` を書いたまま
実行結果の記録ステップで `git push` していた。`github-actions[bot]` が 403 で
弾かれ、**サイトのビルドは成功していたのに記録ステップで落ちて run 全体が
failure になり、deploy ジョブがスキップされた**。

個別に直すのではなく「push するなら contents: write を持っている」を全部の
ワークフローに対して検証する。`tests/test_layer_contract.py` と同じ考え方で、
既定で守られる側に倒す。
"""
import pathlib

import pytest
import yaml

WORKFLOWS = sorted(
    (pathlib.Path(__file__).resolve().parent.parent
     / ".github/workflows").glob("*.yml"))


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(job: dict) -> list[dict]:
    return [s for s in (job.get("steps") or []) if isinstance(s, dict)]


def _writes_to_repo(job: dict) -> bool:
    return any("git push" in (step.get("run") or "") for step in _steps(job))


def _permissions(doc: dict, job: dict) -> dict | str:
    """ジョブに効く権限。ジョブ側があればそれが勝ち、無ければトップレベル。"""
    if "permissions" in job:
        return job["permissions"]
    return doc.get("permissions", {})


def test_ワークフローがある():
    """glob が空でも全テストが通ってしまうのを防ぐ。"""
    assert WORKFLOWS


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_pushするジョブはcontents_writeを持つ(path):
    """read のままだと 403 で落ちる。しかも落ちるのは記録ステップなので、
    本体が成功していても run 全体が failure になり後続ジョブが飛ぶ。"""
    doc = _load(path)
    for name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict) or not _writes_to_repo(job):
            continue
        perms = _permissions(doc, job)

        # 'write-all' なら明示指定は不要
        if perms == "write-all":
            continue
        assert isinstance(perms, dict), (
            f"{path.name} の {name} は git push するのに permissions が "
            f"{perms!r} です")
        assert perms.get("contents") == "write", (
            f"{path.name} の {name} は git push するのに "
            f"contents={perms.get('contents')!r} です。"
            f"github-actions[bot] が 403 で弾かれます。")


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_権限を書いているワークフローは必要な分だけにする(path):
    """`write-all` は事故ったときの被害が読めない。明示的に列挙する。"""
    doc = _load(path)
    tops = [doc.get("permissions")]
    tops += [j.get("permissions") for j in (doc.get("jobs") or {}).values()
             if isinstance(j, dict)]

    for perms in tops:
        assert perms != "write-all", f"{path.name} が write-all を使っています"
