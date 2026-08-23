"""LLM プロバイダの切り替えとアダプタのテスト。

プロバイダは凍結対象ではない（アルゴリズムではなくアダプタ）。ただし
差し替えても呼び出し側が壊れないこと、キー未設定でパイプラインが止まらないこと、
どのプロバイダの推測かが台帳に残ることを固定しておく。
"""
from __future__ import annotations

import pytest

from src.config import Config
from src.llm.gemini import UNSUPPORTED_SCHEMA_KEYS, GeminiClient, _sanitize_schema


# --- プロバイダ切り替え -------------------------------------------------------
def test_既定はGeminiになる():
    """無料枠で運用できるのが Gemini だけなので既定にしている。"""
    client = Config.load().llm_client()

    assert client.provider == "gemini"
    assert client.model.startswith("gemini")


def test_claudeにも切り替えられる():
    """初売上が出たら戻せるようにアダプタを残してある。"""
    config = Config.load()
    config.raw.setdefault("llm", {})["provider"] = "claude"

    client = config.llm_client()

    assert client.provider == "claude"
    assert client.model.startswith("claude")


def test_未知のプロバイダは明示的に失敗する():
    """黙ってフォールバックすると設定ミスに気づけない。"""
    config = Config.load()
    config.raw.setdefault("llm", {})["provider"] = "gpt4all"

    with pytest.raises(ValueError, match="未知の llm.provider"):
        config.llm_client()


def test_モデル名は設定から読む():
    """モデル名は入れ替わる。404 が出たら API のメッセージが後継を教えてくれる。

    2026-08-23: gemini-2.5-flash が新規利用不可になり 404 で全滅した。
    """
    config = Config.load()
    config.raw.setdefault("llm", {})["gemini_model"] = "gemini-9.9-flash"

    assert config.llm_client().model == "gemini-9.9-flash"


def test_キーがなければavailableがFalseになる():
    """呼び出し側はこれを見てテンプレ生成に落ちる。パイプラインは止まらない。"""
    assert GeminiClient(api_key="").available is False
    assert GeminiClient(api_key="dummy").available is True


# --- スキーマの互換性 ---------------------------------------------------------
def test_Geminiが受け付けないスキーマキーを落とす():
    """共通スキーマをそのまま渡すと 400 になる。"""
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 20}},
        "required": ["score"],
        "additionalProperties": False,
    }

    sanitized = _sanitize_schema(schema)

    assert "additionalProperties" not in sanitized
    assert "minimum" not in sanitized["properties"]["score"]
    assert sanitized["properties"]["score"]["type"] == "integer"
    assert sanitized["required"] == ["score"]


def test_実際の採点スキーマが通る形になる():
    from src.scout.scoring import SCORE_SCHEMA

    sanitized = _sanitize_schema(SCORE_SCHEMA)

    def _walk(node):
        if isinstance(node, dict):
            for key in UNSUPPORTED_SCHEMA_KEYS:
                assert key not in node, f"{key} が残っている"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(sanitized)
    assert sanitized["properties"]["verdict"]["enum"]      # enum は残す


def test_元のスキーマを壊さない():
    """共通スキーマは Claude 側でも使うので破壊してはいけない。"""
    schema = {"type": "object", "additionalProperties": False}

    _sanitize_schema(schema)

    assert schema["additionalProperties"] is False


# --- レスポンスの解釈 ---------------------------------------------------------
def test_安全性ブロック時は空文字を返す():
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}}

    assert GeminiClient._text(blocked) == ""


def test_グラウンディングから参照URLを集める():
    """ここが SERP 代理指標の入力になる。"""
    data = {"candidates": [{"groundingMetadata": {"groundingChunks": [
        {"web": {"uri": "https://a.example", "title": "A"}},
        {"web": {"uri": "https://b.example", "title": "B"}},
        {"web": {"uri": "https://a.example", "title": "重複"}},
    ]}}]}

    results = GeminiClient._collect_results(data)

    assert [r["url"] for r in results] == ["https://a.example", "https://b.example"]


def test_グラウンディングがなくても落ちない():
    assert GeminiClient._collect_results({"candidates": [{}]}) == []
    assert GeminiClient._collect_results({}) == []


# --- 台帳への記録 -------------------------------------------------------------
def test_どのプロバイダの予測かが台帳に残る(tmp_path):
    """プロバイダを変えると inferred スコアの分布が変わるので、校正時に
    別物として扱えるようにしておく必要がある。"""
    from src.scout.ledger import ExperimentLedger
    from src.scout.models import Candidate, Opportunity, Score

    ledger = ExperimentLedger(tmp_path)
    opportunity = Opportunity(id="abc", candidate=Candidate(title="ネタ"),
                              score=Score(demand=10, scored=True))

    prediction = ledger.record_prediction(
        opportunity, "n_abc", llm_provider="gemini", llm_model="gemini-2.5-flash")

    assert prediction.llm_provider == "gemini"
    assert prediction.llm_model == "gemini-2.5-flash"
    assert ledger.rows("prediction")[0]["llm_provider"] == "gemini"
