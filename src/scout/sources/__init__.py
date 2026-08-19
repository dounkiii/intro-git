"""発掘元アダプタ。差し替え可能にしてあるのは、Grok / X API / 将来の別サービスを
入れ替えてもパイプライン本体を触らずに済むようにするため。"""
from .base import Candidate, ScoutSource
from .grok import GrokSource
from .x_api import XApiSource

__all__ = ["Candidate", "ScoutSource", "GrokSource", "XApiSource"]
