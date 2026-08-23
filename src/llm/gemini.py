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
import random
import time
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

# 再試行する HTTP ステータス。429=レート上限、503=一時的な高負荷、500/502/504=一時障害。
RETRYABLE_STATUS = (429, 500, 502, 503, 504)


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

    def __init__(self, api_key: str, model: str = "gemini-3.6-flash",
                 effort: str = "medium", max_tokens: int = 8000,
                 timeout: int = 120, max_retries: int = 3,
                 min_interval: float = 6.0):
        """`min_interval` は連続呼び出しの最小間隔（秒）。

        無料枠は分あたりの回数制限が厳しく、間を空けずに投げると 1 回目から
        429 になる。1日1回のジョブなので待つ余裕はある。
        """
        self.api_key = api_key
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._last_call_at = 0.0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    def _throttle(self) -> None:
        """前回の呼び出しから `min_interval` 秒空ける。無料枠の分あたり制限対策。"""
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_call_at)
        if wait > 0 and self._last_call_at:
            time.sleep(wait)

    def _post(self, payload: dict) -> dict | None:
        """429 / 503 は待って再試行する。それ以外のエラーは即座に諦める。

        再試行を入れているのは、1日1回のジョブなので待つ時間の余裕があるのに、
        一時的なレート上限や高負荷で「未採点」に落ちるのが損だから。
        """
        for attempt in range(self.max_retries + 1):
            self._throttle()
            self._last_call_at = time.monotonic()
            try:
                resp = requests.post(
                    f"{API_ROOT}/{self.model}:generateContent",
                    params={"key": self.api_key},
                    json=payload, timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                detail, retry_after = self._error_detail(exc.response)

                if status in RETRYABLE_STATUS and attempt < self.max_retries:
                    delay = retry_after or self._backoff(attempt)
                    logger.warning("Gemini が %s を返しました。%.0f秒待って再試行します"
                                   "（%d/%d）: %s", status, delay, attempt + 1,
                                   self.max_retries, detail or "-")
                    time.sleep(delay)
                    continue

                self._log_final_error(status, detail)
                return None
            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    logger.warning("Gemini への接続に失敗（%s）。%.0f秒待って再試行します"
                                   "（%d/%d）。", type(exc).__name__, delay,
                                   attempt + 1, self.max_retries)
                    time.sleep(delay)
                    continue
                logger.warning("Gemini API 呼び出しに失敗しました（%s）。テンプレ生成に"
                               "切り替えます。", type(exc).__name__)
                return None
        return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        """指数バックオフ + ジッタ。同時実行が揃って再試行するのを避ける。"""
        return min(60.0, 5.0 * (2 ** attempt)) + random.uniform(0, 3)

    @staticmethod
    def _error_detail(response) -> tuple[str, float | None]:
        """エラー本文と、サーバーが指定した再試行待ち秒数を取り出す。"""
        if response is None:
            return "", None
        try:
            error = response.json().get("error", {})
        except Exception:
            return "", None

        retry_after = None
        for item in error.get("details", []) or []:
            raw = item.get("retryDelay")
            if isinstance(raw, str) and raw.endswith("s"):
                try:
                    retry_after = float(raw[:-1])
                except ValueError:
                    pass
        return error.get("message", "")[:300], retry_after

    @staticmethod
    def _log_final_error(status: int, detail: str) -> None:
        if status == 404 and "no longer available" in detail:
            logger.warning("Gemini API がエラーを返しました（404）: %s", detail)
            logger.warning("モデル名が古くなっています。config.yaml の "
                           "llm.gemini_model を上のメッセージが示す名前に変更してください。")
        elif status == 429:
            logger.warning("Gemini の無料枠のレート上限に当たりました（再試行しても"
                           "解消せず）。config.yaml の scout.research_limit を下げるか、"
                           "llm.min_interval_seconds を上げてください。")
        else:
            logger.warning("Gemini API がエラーを返しました（%s）: %s", status, detail)

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
