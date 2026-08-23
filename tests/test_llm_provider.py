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


# --- リトライとスロットリング -------------------------------------------------
class _FakeResponse:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)


def _client(monkeypatch, responses: list, **kwargs):
    """`responses` を順に返す偽の requests.post を仕込んだクライアントを返す。"""
    import src.llm.gemini as gemini

    calls: list[float] = []
    monkeypatch.setattr(gemini.time, "sleep", lambda s: calls.append(s))
    monkeypatch.setattr(gemini.requests, "post",
                        lambda *a, **k: responses.pop(0))
    client = GeminiClient(api_key="dummy", min_interval=0, **kwargs)
    return client, calls


OK_BODY = {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]}


def test_レート上限は待って再試行する(monkeypatch):
    """429 で1回諦めると「未採点」に落ちる。1日1回のジョブなら待つ余裕がある。"""
    responses = [_FakeResponse(429, {"error": {"message": "rate"}}),
                 _FakeResponse(200, OK_BODY)]
    client, sleeps = _client(monkeypatch, responses)

    result = client.generate_json("s", "p", {"type": "object"})

    assert result == {"a": 1}
    assert len(sleeps) == 1          # 1回待った


def test_高負荷の503も再試行する(monkeypatch):
    responses = [_FakeResponse(503, {"error": {"message": "high demand"}}),
                 _FakeResponse(200, OK_BODY)]
    client, _ = _client(monkeypatch, responses)

    assert client.generate_json("s", "p", {"type": "object"}) == {"a": 1}


def test_サーバー指定の待ち時間を優先する(monkeypatch):
    """retryDelay があれば自前のバックオフより優先する。"""
    responses = [
        _FakeResponse(429, {"error": {"message": "rate",
                                      "details": [{"retryDelay": "27s"}]}}),
        _FakeResponse(200, OK_BODY),
    ]
    client, sleeps = _client(monkeypatch, responses)

    client.generate_json("s", "p", {"type": "object"})

    assert sleeps == [27.0]


def test_再試行しても駄目なら諦める(monkeypatch):
    responses = [_FakeResponse(429, {"error": {"message": "rate"}}) for _ in range(3)]
    client, sleeps = _client(monkeypatch, responses, max_retries=2)

    assert client.generate_json("s", "p", {"type": "object"}) is None
    assert len(sleeps) == 2


def test_モデル名の404は再試行しない(monkeypatch):
    """設定ミスなので待っても直らない。即座に諦めて警告を出す。"""
    responses = [_FakeResponse(404, {"error": {"message": "no longer available"}})]
    client, sleeps = _client(monkeypatch, responses)

    assert client.generate_json("s", "p", {"type": "object"}) is None
    assert sleeps == []              # 待っていない


def test_バックオフは上限内で増える():
    delays = [GeminiClient._backoff(i) for i in range(5)]

    assert delays == sorted(delays)
    assert all(d <= 63 for d in delays)


def test_呼び出し間隔を空ける(monkeypatch):
    """無料枠は分あたりの制限が厳しく、連続で投げると1回目から429になる。"""
    import src.llm.gemini as gemini

    slept: list[float] = []
    monkeypatch.setattr(gemini.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(gemini.requests, "post",
                        lambda *a, **k: _FakeResponse(200, OK_BODY))
    client = GeminiClient(api_key="dummy", min_interval=6.0)

    client.generate_json("s", "p", {"type": "object"})   # 1回目は待たない
    assert slept == []

    client.generate_json("s", "p", {"type": "object"})   # 2回目は間隔を空ける
    assert slept and slept[0] > 0


# --- ワークフローの環境変数の取り違え防止 -------------------------------------
def test_探索と制作の両方にAFF環境変数が渡っている():
    """探索レイヤも AFF_* から換金経路を実測する（Scorer._has_affiliate_route）。

    2026-08-23: daily-scout.yml に AFF_* を渡し忘れていたため、シークレットを
    登録しても monetization_observed が常に False になり、すべての候補が
    「案件未設定」判定になっていた。
    """
    import pathlib
    import re

    import yaml

    config = yaml.safe_load(pathlib.Path("config.yaml").read_text(encoding="utf-8"))
    monetization = config["monetization"]
    needed = {monetization["hub_url_slot"], monetization["product_url_slot"]}
    for offers in monetization["offers"].values():
        needed.update(o["slot"] for o in offers)

    for workflow in ("daily-scout.yml", "daily-generate.yml", "approve-command.yml"):
        text = pathlib.Path(".github/workflows") / workflow
        content = text.read_text(encoding="utf-8")
        passed = set(re.findall(r"(AFF_[A-Z_]+):", content))
        missing = needed - passed
        assert not missing, f"{workflow} に渡っていない: {sorted(missing)}"
