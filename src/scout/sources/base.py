"""発掘元の共通インターフェース。"""
from __future__ import annotations

from typing import Protocol

from ..models import Candidate

__all__ = ["Candidate", "ScoutSource"]


class ScoutSource(Protocol):
    """発掘元アダプタ。

    `available` が False のときはパイプラインが自動的にスキップする。
    キーを1つも持っていない状態でも `--sample` で全体が動くようにしている。
    """

    name: str

    @property
    def available(self) -> bool: ...

    def discover(self, limit: int) -> list[Candidate]: ...
