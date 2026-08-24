"""運用の記録。スケジュール実行の結果をリポジトリに残す。

`api.github.com` がプロキシで止まる環境でも、git だけで昨夜の実行を追えるように
するためのもの。詳細は `runlog.py` の docstring。
"""
from .runlog import MARKERS, RunLog, RunRecord, scan

__all__ = ["MARKERS", "RunLog", "RunRecord", "scan"]
