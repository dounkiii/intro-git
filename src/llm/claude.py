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

    def research(self, system: str, prompt: str, max_uses: int = 6,
                 tool_type: str = "web_search_20260209") -> tuple[str, list[dict]] | None:
        """web_search サーバーツールで裏取りし、(本文, 検索結果) を返す。

        検索結果は [{"url": ..., "title": ...}, ...]。タイトルは SERP のドメイン種別
        分類と検索意図の一致率判定（src/scout/serp.py）に使う。

        ちゃっぴー案では Gemini に担当させていた工程。Claude のサーバー側 web_search を
        使えば「検索して読んで書く」が1リクエストで済むため、プロバイダを増やさずに
        同じことができる。失敗時は None（呼び出し側は検索なしにフォールバックする）。

        `tool_type` はモデルによって対応版が違うため設定で差し替え可能にしている。
        """
        client = self._ensure_client()
        if client is None:
            return None

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": tool_type, "name": "web_search", "max_uses": max_uses}],
                output_config={"effort": self.effort},
            )
        except Exception as exc:
            logger.warning("web_search 付きの呼び出しに失敗しました（%s）。検索なしで続行します。",
                           type(exc).__name__)
            return None

        if response.stop_reason == "refusal":
            logger.warning("Claude が調査を拒否しました。この候補はスキップします。")
            return None

        text = "\n".join(b.text for b in response.content if b.type == "text")
        return text, self._collect_results(response)

    @staticmethod
    def _collect_results(response) -> list[dict]:
        """web_search の結果ブロックから URL とタイトルを集める。

        サーバーツールのエラーは例外ではなく 200 で返り、成功時の `content` は
        リスト、エラー時はオブジェクトになる。indexing する前に型で分岐する。
        """
        results: list[dict] = []
        seen: set[str] = set()
        for block in response.content:
            if getattr(block, "type", "") != "web_search_tool_result":
                continue
            content = getattr(block, "content", None)
            if not isinstance(content, list):
                code = getattr(content, "error_code", None)
                logger.warning("web_search がエラーを返しました: %s", code)
                continue
            for result in content:
                url = getattr(result, "url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append({"url": url, "title": getattr(result, "title", "") or ""})
        return results
