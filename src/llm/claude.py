"""Claude API による原稿生成。

- 公式 SDK (`anthropic`) を使う。未インストール / APIキー未設定 / API エラーの
  いずれでもパイプラインを止めず `None` を返し、呼び出し側がテンプレ生成へ
  フォールバックできるようにしている（毎朝の cron が 1 回の障害で止まらないため）。
- 出力は structured outputs (`output_config.format`) で JSON に固定する。
  自由文をパースするとフォーマット崩れで承認キューが汚れる。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Claude Messages API の薄いラッパー。JSON スキーマ準拠の dict を返す。"""

    def __init__(self, api_key: str, model: str = "claude-opus-5",
                 effort: str = "medium", max_tokens: int = 8000):
        self.api_key = api_key
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = None

    @property
    def available(self) -> bool:
        """API キーと SDK が揃っているか。false ならフォールバックすべき。"""
        return bool(self.api_key) and self._ensure_client() is not None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        try:
            import anthropic
        except ImportError:
            logger.warning("anthropic SDK が未インストールです。`pip install anthropic`")
            return None
        self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate_json(self, system: str, prompt: str,
                      schema: dict[str, Any]) -> dict[str, Any] | None:
        """JSON スキーマに従った dict を返す。失敗時は None。"""
        client = self._ensure_client()
        if client is None:
            return None

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except Exception as exc:  # SDK の例外階層に依存せず、生成失敗は一律フォールバック
            logger.warning("Claude API 呼び出しに失敗しました（%s）。テンプレ生成に切り替えます。",
                           type(exc).__name__)
            return None

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            logger.warning("Claude が生成を拒否しました（category=%s）。この案件はスキップします。",
                           getattr(detail, "category", None))
            return None

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            logger.warning("Claude のレスポンスにテキストがありません。")
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Claude のレスポンスが JSON として読めませんでした。")
            return None
