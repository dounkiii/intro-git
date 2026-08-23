"""Gemini API による原稿生成。Claude アダプタと同じインターフェース。

採用理由（docs/RESEARCH_SYSTEM.md 第7ラウンド）:
  無料枠で運用できる唯一の選択肢だから。呼び出しは1日約24回で、
  Flash 系の無料枠に収まる。売上0円の段階でランニングコストを持たない方が、
  スコア精度より優先度が高いという判断。

実装上の注意:
- `responseSchema` は JSON Schema の全キーワードを受け付けない（`additionalProperties`
  や `minimum` / `maximum` は非対応）。共通スキーマをそのまま渡すと 400 になるので
  `_sanitize_schema` で落としている。
- Google 検索グラウンディングと `responseSchema` の併用は保証されていない。
  そのため既存設計どおり「検索して読む」と「構造化する」を2回に分ける。
  結果的に Claude アダプタと同じ呼び出し形になっている。
- 公式 SDK ではなく `requests` を使う。依存を増やさずに済み、
  障害時に素の HTTP として切り分けやすいため。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Gemini の responseSchema が受け付けないキーワード。残すと 400 になる。
UNSUPPORTED_SCHEMA_KEYS = ("additionalProperties", "minimum", "maximum",
                           "exclusiveMinimum", "exclusiveMaximum", "$schema")

# effort（Claude 側の概念）を思考予算に読み替える。0 で思考を切る。
EFFORT_THINKING_BUDGET = {"low": 0, "medium": 2048, "high": 8192,
                          "xhigh": 16384, "max": 24576}


def _sanitize_schema(schema: Any) -> Any:
    """Gemini が受け付ける形にスキーマを削る。共通スキーマを壊さないため再帰コピー。"""
    if isinstance(schema, dict):
        return {k: _sanitize_schema(v) for k, v in schema.items()
                if k not in UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(schema, list):
        return [_sanitize_schema(v) for v in schema]
    return schema


class GeminiClient:
    """Gemini generateContent の薄いラッパー。ClaudeClient と同じ3メソッドを持つ。"""

    provider = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 effort: str = "medium", max_tokens: int = 8000,
                 timeout: int = 120):
        self.api_key = api_key
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    def _post(self, payload: dict) -> dict | None:
        try:
            resp = requests.post(
                f"{API_ROOT}/{self.model}:generateContent",
                params={"key": self.api_key},
                json=payload, timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            detail = ""
            try:
                detail = exc.response.json().get("error", {}).get("message", "")[:300]
            except Exception:
                pass
            if status == 429:
                logger.warning("Gemini の無料枠のレート上限に当たりました。"
                               "config.yaml の scout.research_limit を下げてください。")
            else:
                logger.warning("Gemini API がエラーを返しました（%s）: %s", status, detail)
            return None
        except requests.RequestException as exc:
            logger.warning("Gemini API 呼び出しに失敗しました（%s）。テンプレ生成に"
                           "切り替えます。", type(exc).__name__)
            return None

    def _generation_config(self, extra: dict | None = None) -> dict:
        config: dict[str, Any] = {"maxOutputTokens": self.max_tokens}
        budget = EFFORT_THINKING_BUDGET.get(self.effort)
        if budget is not None:
            config["thinkingConfig"] = {"thinkingBudget": budget}
        config.update(extra or {})
        return config

    @staticmethod
    def _text(data: dict) -> str:
        """candidates からテキストを取り出す。安全性ブロック時は空文字。"""
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = (data.get("promptFeedback") or {}).get("blockReason")
            if feedback:
                logger.warning("Gemini が生成をブロックしました（%s）。", feedback)
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)

    # ------------------------------------------------------------------
    def generate_json(self, system: str, prompt: str,
                      schema: dict[str, Any]) -> dict[str, Any] | None:
        """JSON スキーマに従った dict を返す。失敗時は None。"""
        if not self.available:
            return None

        data = self._post({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": self._generation_config({
                "responseMimeType": "application/json",
                "responseSchema": _sanitize_schema(schema),
            }),
        })
        if data is None:
            return None

        text = self._text(data)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini のレスポンスが JSON として読めませんでした。")
            return None

    def research(self, system: str, prompt: str, max_uses: int = 6,
                 tool_type: str = "") -> tuple[str, list[dict]] | None:
        """Google 検索グラウンディングで裏取りし、(本文, 検索結果) を返す。

        `tool_type` は Claude 側との互換のために受け取るだけで使わない。
        `max_uses` も Gemini 側に相当する指定が無いため無視する（グラウンディングの
        検索回数はモデルが決める）。
        """
        if not self.available:
            return None

        data = self._post({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # responseSchema とは併用しない（保証されていない）。ここは自由文で受け、
            # 構造化は generate_json の2回目の呼び出しで行う。
            "tools": [{"google_search": {}}],
            "generationConfig": self._generation_config(),
        })
        if data is None:
            return None

        return self._text(data), self._collect_results(data)

    @staticmethod
    def _collect_results(data: dict) -> list[dict]:
        """groundingMetadata から URL とタイトルを集める。

        ここが SERP 代理指標（src/scout/serp.py）の入力になる。Google 検索の
        結果なので、Claude の web_search より実際の SERP に近い。
        """
        candidates = data.get("candidates") or []
        if not candidates:
            return []
        metadata = candidates[0].get("groundingMetadata") or {}

        results: list[dict] = []
        seen: set[str] = set()
        for chunk in metadata.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            url = web.get("uri", "")
            if not url or url in seen:
                continue
            seen.add(url)
            results.append({"url": url, "title": web.get("title", "") or ""})
        return results
