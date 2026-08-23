"""設定・環境変数の読み込み。

`config.yaml`（動作パラメータ）と `.env`（秘密情報）を統合して提供する。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:  # .env の読み込み（未インストールでも動くようフォールバック）
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
REVIEW_DIR = DATA_DIR / "review_queue"
ARTICLE_DIR = DATA_DIR / "articles"


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    """実行時設定。`config.yaml` + 環境変数をまとめたもの。"""

    raw: dict[str, Any] = field(default_factory=dict)

    # secrets
    x_bearer_token: str = ""
    tiktok_access_token: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # GitHub（承認 Issue の作成・更新に使う。Actions 内では自動で入る）
    github_token: str = ""
    github_repository: str = ""

    # safety switches
    dry_run: bool = True
    review_required: bool = True

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        cfg_path = Path(path) if path else ROOT / "config.yaml"
        raw: dict[str, Any] = {}
        if cfg_path.exists():
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        ARTICLE_DIR.mkdir(parents=True, exist_ok=True)

        return cls(
            raw=raw,
            x_bearer_token=os.getenv("X_BEARER_TOKEN", ""),
            tiktok_access_token=os.getenv("TIKTOK_ACCESS_TOKEN", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_repository=os.getenv("GITHUB_REPOSITORY", ""),
            dry_run=_bool_env("DRY_RUN", True),
            review_required=_bool_env("REVIEW_REQUIRED", True),
        )

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {}) or {}

    def llm_client(self):
        """`llm.provider` に従ったクライアントを返す。

        キー未設定でも生成し、呼び出し側は `available` を見てテンプレ生成に
        フォールバックする。プロバイダは凍結対象ではない（アルゴリズムではなく
        アダプタなので、docs/OPERATIONS.md §3 に含まれない）。
        """
        llm = self.section("llm")
        provider = (llm.get("provider") or "gemini").lower()
        effort = llm.get("effort", "medium")
        max_tokens = int(llm.get("max_tokens", 8000))

        if provider == "gemini":
            from .llm import GeminiClient

            return GeminiClient(
                api_key=self.gemini_api_key,
                model=llm.get("gemini_model", "gemini-2.5-flash"),
                effort=effort, max_tokens=max_tokens,
            )

        if provider == "claude":
            from .llm import ClaudeClient

            return ClaudeClient(
                api_key=self.anthropic_api_key,
                model=llm.get("model", "claude-sonnet-5"),
                effort=effort, max_tokens=max_tokens,
            )

        raise ValueError(f"未知の llm.provider です: {provider}（gemini | claude）")
