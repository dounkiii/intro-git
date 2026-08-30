"""テストが実データを書き換えないようにする。

2026-08-25: `adopt()` にストアへの書き戻しを足したところ、ストアを
monkeypatch していなかった既存テストが **リポジトリの
data/scout/opportunities.jsonl に本物の行を追記した**。テストは通るので
気づけず、コミット直前の差分で初めて分かった。

2026-08-30: 同じ事故が `data/review_queue/` で再発した。`test_pipeline.py` が
本番の承認キューに向けてパイプラインを流し、**その朝に生成された記事3件を
テンプレ出力で上書きした**。サンプルの item_id（`tax-sample-t1` など）が
本番と同じ ID だったため、新規追加ではなく上書きになっている。

**なぜ1回目の対策で止まらなかったか。** 監視対象を「見るファイルの一覧」で
書いていたので、**そこに載っていない新しい状態ファイルは最初から素通り**
だった。`data/review_queue/` は一覧に無かった。守る側を列挙する設計は、
守り漏れが静かに増えていく。

そこで **data/ 配下を全部見て、除外する方を理由付きで列挙する**形に変えた
（`tests/test_layer_contract.py` の `FUNNEL_EXEMPT` と同じ考え方）。
新しい状態ファイルが増えたときに、既定で守られる側に倒す。
"""
import hashlib
import pathlib

import pytest

from src.config import DATA_DIR

# 監視から外すもの。**必ず理由を書く。** 理由なしの除外を許すと、
# ここが守り漏れの隠し場所になる。
EXEMPT = {
    "sample_tweets.json": "入力サンプル。テストは読むだけ",
    "scout/sample_candidates.json": "入力サンプル。テストは読むだけ",
}


def _digest() -> dict[str, str]:
    """data/ 配下の全ファイルのハッシュ。除外したものは見ない。"""
    out: dict[str, str] = {}
    if not DATA_DIR.exists():
        return out
    for p in sorted(DATA_DIR.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(DATA_DIR))
        if rel in EXEMPT or rel.endswith(".gitkeep"):
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(autouse=True)
def _real_data_is_untouched():
    before = _digest()
    yield
    after = _digest()

    changed = sorted(k for k in before if after.get(k) != before[k])
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))

    assert not (changed or added or removed), (
        "テストがリポジトリの実データを触りました:\n"
        f"  書き換え: {changed}\n  追加: {added}\n  削除: {removed}\n"
        "tmp_path に出力先を逃がすか、store / queue / ledger の path を "
        "monkeypatch してください。サンプルの ID は本番と同じなので、"
        "逃がさないと本物の記事を上書きします。"
    )

