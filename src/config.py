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
    threads_access_token: str = ""
    threads_user_id: str = ""
    openai_api_key: str = ""

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

        return cls(
            raw=raw,
            x_bearer_token=os.getenv("X_BEARER_TOKEN", ""),
            tiktok_access_token=os.getenv("TIKTOK_ACCESS_TOKEN", ""),
            threads_access_token=os.getenv("THREADS_ACCESS_TOKEN", ""),
            threads_user_id=os.getenv("THREADS_USER_ID", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            dry_run=_bool_env("DRY_RUN", True),
            review_required=_bool_env("REVIEW_REQUIRED", True),
        )

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {}) or {}
