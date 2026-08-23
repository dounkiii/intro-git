"""LLM 連携。プロバイダは `config.yaml` の `llm.provider` で切り替える。

インターフェースは3つだけに閉じてある（available / generate_json / research）ので、
プロバイダの追加はアダプタ1ファイルで済む。
"""
from .claude import ClaudeClient
from .gemini import GeminiClient

__all__ = ["ClaudeClient", "GeminiClient"]
