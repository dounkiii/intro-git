"""テストが実データを書き換えないようにする。

2026-08-25: `adopt()` にストアへの書き戻しを足したところ、ストアを
monkeypatch していなかった既存テストが **リポジトリの
data/scout/opportunities.jsonl に本物の行を追記した**。テストは通るので
気づけず、コミット直前の差分で初めて分かった。

同じ事故を落とすため、テストの前後で data/ 配下のファイルを突き合わせる。
"""
import hashlib
import pathlib

import pytest

from src.config import DATA_DIR

# 生成物は毎回変わるので対象外。状態ファイルだけを見る。
WATCHED = ("scout/opportunities.jsonl", "scout/ledger.jsonl",
           "adopted_niches.yaml", "posts.csv", "revenue.csv",
           "ops/runs.jsonl")


def _digest() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in WATCHED:
        p = DATA_DIR / rel
        out[rel] = (hashlib.sha256(p.read_bytes()).hexdigest()
                    if p.exists() else None)
    return out


@pytest.fixture(autouse=True)
def _real_data_is_untouched():
    before = _digest()
    yield
    after = _digest()
    changed = [k for k in WATCHED if before[k] != after[k]]
    assert not changed, (
        f"テストがリポジトリの実データを書き換えました: {changed}\n"
        f"tmp_path を使うか、store / ledger / niches の path を "
        f"monkeypatch してください。")
