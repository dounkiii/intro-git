"""自動レビュワーのテスト。

一番守りたいのは「同意しかできない状態を作らない」こと。LLM レビュワーは
既定で迎合するので、そこが崩れるとレビューがノイズになる。
"""
from src.review.critic import CRITIQUE_SCHEMA, Critic, CritiqueResult


class _FakeLLM:
    provider = "fake"
    model = "fake-1"
    api_key_env = "FAKE_API_KEY"
    available = True

    def __init__(self, payload=None):
        self.payload = payload
        self.calls: list[tuple] = []

    def generate_json(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        return self.payload


class _UnavailableLLM(_FakeLLM):
    available = False


def test_指摘には破綻する条件が必須():
    """同意する場合も破綻条件を書かせる。「妥当です」だけを返せなくする。"""
    finding = CRITIQUE_SCHEMA["properties"]["findings"]["items"]

    assert "breaks_when" in finding["required"]
    assert "detail" in finding["required"]
    assert "severity" in finding["required"]


def test_具体的な指摘がない回を検出する():
    """同意のみが続くならレビュー自体をやめる材料にする。"""
    agreed = CritiqueResult(findings=[{"severity": "consider", "title": "t",
                                       "detail": "d", "breaks_when": "b"}])
    flagged = CritiqueResult(findings=[{"severity": "should_fix", "title": "t",
                                        "detail": "d", "breaks_when": "b"}])

    assert agreed.agreed_only
    assert not flagged.agreed_only


def test_同意のみの回はレポートに明記される():
    body = CritiqueResult(headline="h").render()

    assert "blocker / should_fix が0件" in body


def test_凍結対象への提案は指摘ではなく別枠に出る():
    """20件未満でアルゴリズムを触る口実にしないため、指摘と分けて表示する。"""
    result = CritiqueResult(
        headline="h",
        frozen_violation=["配点を 20 → 25 に変えるべき"],
        findings=[{"severity": "should_fix", "title": "t", "detail": "d",
                   "breaks_when": "b"}])

    body = result.render()

    assert "凍結対象への変更提案" in body
    assert "記録のみ" in body or "実装しません" in body


def test_凍結契約をレビュワーに渡す():
    """契約を渡さないと、凍結対象への提案を却下できない。"""
    llm = _FakeLLM({"headline": "h", "findings": [], "answers": []})

    Critic(llm=llm).critique("依頼本文", contract="触らないもの: 100点の配点")

    _, prompt, _ = llm.calls[0]
    assert "触らないもの: 100点の配点" in prompt
    assert "依頼本文" in prompt


def test_同意だけを返させない指示がシステムプロンプトに入る():
    llm = _FakeLLM({"headline": "h", "findings": [], "answers": []})

    Critic(llm=llm).critique("依頼")

    system, _, _ = llm.calls[0]
    assert "同意だけを返さない" in system


def test_APIキーが無ければ黙って諦める():
    """レビューが動かないことでパイプラインを止めない。"""
    assert Critic(llm=_UnavailableLLM()).critique("依頼") is None


def test_生成失敗でも例外を投げない():
    assert Critic(llm=_FakeLLM(None)).critique("依頼") is None


def test_レビュワーのプロバイダを記録する():
    """Claude 期と Gemini 期のレビューを同じものとして扱わないため。"""
    llm = _FakeLLM({"headline": "h", "findings": [], "answers": []})

    result = Critic(llm=llm).critique("依頼")

    assert result.provider == "fake"
    assert result.model == "fake-1"
    assert "fake" in result.render()


def test_設計レビューは承認キューとは別のラベルを使う():
    """承認ワークフローが design-review Issue のコメントで誤発火しないこと。"""
    import pathlib

    from src.config import Config

    approval = Config.load().section("approval")
    review_label = approval["review_label"]

    assert review_label != approval["label"]
    workflow = pathlib.Path(".github/workflows/approve-command.yml").read_text(
        encoding="utf-8")
    assert f"'{review_label}'" not in workflow
