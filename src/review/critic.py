"""レビュー依頼を LLM に投げ、構造化された指摘を受け取る。

設計の要点は「同意しかできない状態を作らない」こと。LLM レビュワーは既定で
迎合するので、スキーマ側で具体性を要求する。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config

logger = logging.getLogger(__name__)

REQUEST_PATH = Path("docs/REVIEW_REQUEST.md")

# 凍結契約。レビュワーにも渡し、ここへの変更提案は却下対象として扱わせる。
CONTRACT_PATH = Path("docs/OPERATIONS.md")

SYSTEM = """あなたは実装済みシステムの設計レビュワーです。相手は実装者（Claude Code）で、
あなたの仕事は**実装者が見落としている問題を挙げること**です。

守ること:

1. **同意だけを返さない。** 「妥当です」で終わる回答は価値がありません。
   同意する場合も、その判断が破綻する条件を1つ以上挙げてください。
2. **凍結契約を尊重する。** 提示された「凍結対象」への変更提案はしないでください。
   実績データが無いと正しく直せないと合意済みの項目です。提案したい場合は
   `frozen_violation` に入れてください（実装者が却下判断に使います）。
3. **推測と観測を混ぜない。** 「たぶんこうなっている」で指摘しないでください。
   確認が必要な場合は `needs_check` として、何をどう確認すれば分かるかを書く。
4. 日本語で答えてください。
5. 実装者は「事実 / 診断 / 根拠 / 判定」を分けて読みます。断定できないものを
   断定形で書かないでください。"""

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string",
                                 "enum": ["blocker", "should_fix", "consider"]},
                    "detail": {"type": "string"},
                    # 同意する指摘でも、破綻する条件を書かせる
                    "breaks_when": {"type": "string"},
                },
                "required": ["title", "severity", "detail", "breaks_when"],
            },
        },
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["question", "recommendation", "reasoning"],
            },
        },
        "needs_check": {"type": "array", "items": {"type": "string"}},
        "frozen_violation": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "findings", "answers"],
}


@dataclass
class CritiqueResult:
    headline: str = ""
    findings: list[dict] = field(default_factory=list)
    answers: list[dict] = field(default_factory=list)
    needs_check: list[str] = field(default_factory=list)
    frozen_violation: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""

    @property
    def agreed_only(self) -> bool:
        """具体的な指摘が無い回。続くならレビュー自体をやめる材料にする。"""
        return not any(f.get("severity") in ("blocker", "should_fix")
                       for f in self.findings)

    def render(self) -> str:
        """Issue コメント用の Markdown。"""
        lines = [f"## {self.headline or 'レビュー結果'}", ""]

        if self.frozen_violation:
            lines += ["> ⚠️ **凍結対象への変更提案が含まれています。**"
                      "実績20件までは記録のみで、実装しません。", ""]
            lines += [f"> - {v}" for v in self.frozen_violation] + [""]

        if self.findings:
            lines += ["### 指摘", ""]
            order = {"blocker": 0, "should_fix": 1, "consider": 2}
            mark = {"blocker": "🛑 blocker", "should_fix": "⚠️ should_fix",
                    "consider": "💭 consider"}
            for f in sorted(self.findings,
                            key=lambda x: order.get(x.get("severity"), 9)):
                lines += [
                    f"**{mark.get(f.get('severity'), '?')} — {f.get('title', '')}**",
                    "",
                    f.get("detail", ""),
                    "",
                    f"　破綻する条件: {f.get('breaks_when', '（未記入）')}",
                    "",
                ]
        else:
            lines += ["### 指摘", "", "なし（具体的な指摘が返らなかった回）", ""]

        if self.answers:
            lines += ["### 質問への回答", ""]
            for a in self.answers:
                lines += [
                    f"**Q: {a.get('question', '')}**",
                    "",
                    f"→ {a.get('recommendation', '')}",
                    "",
                    f"　理由: {a.get('reasoning', '')}",
                    "",
                ]

        if self.needs_check:
            lines += ["### 確認が必要（推測で断定していない項目）", ""]
            lines += [f"- {c}" for c in self.needs_check] + [""]

        lines += ["---",
                  f"_レビュワー: {self.provider} / {self.model}_"]
        if self.agreed_only:
            lines.append("_※ この回は blocker / should_fix が0件です。"
                         "同意のみが続くならレビュー自体の費用対効果を見直します。_")
        return "\n".join(lines)


class Critic:
    """レビュー依頼を LLM に投げる。

    プロバイダは `config.yaml` の `llm.provider` に従う（凍結対象ではない）。
    Gemini 無料枠でも動くので、レビューを回すのに課金は要らない。
    """

    def __init__(self, config: Config | None = None, llm=None):
        self.config = config or Config.load()
        self.llm = llm or self.config.llm_client()

    def critique(self, request: str, contract: str = "") -> CritiqueResult | None:
        """依頼文からレビュー結果を作る。LLM が使えないときは None。"""
        if not self.llm.available:
            logger.warning("LLM が使えないためレビューをスキップします（provider=%s）。"
                           "%s を登録してください。",
                           getattr(self.llm, "provider", "?"),
                           getattr(self.llm, "api_key_env", "API キー"))
            return None

        prompt = f"""以下がレビュー依頼です。

{request}
"""
        if contract:
            prompt += f"""
---

以下は**凍結契約**です。ここに「触らない」と書かれている項目への変更提案は
`frozen_violation` に入れてください（指摘としては挙げないでください）。

{contract}
"""
        data = self.llm.generate_json(SYSTEM, prompt, CRITIQUE_SCHEMA)
        if not data:
            logger.warning("レビューの生成に失敗しました（provider=%s）",
                           getattr(self.llm, "provider", "?"))
            return None

        return CritiqueResult(
            headline=data.get("headline", ""),
            findings=data.get("findings") or [],
            answers=data.get("answers") or [],
            needs_check=data.get("needs_check") or [],
            frozen_violation=data.get("frozen_violation") or [],
            provider=getattr(self.llm, "provider", ""),
            model=getattr(self.llm, "model", ""),
        )

    @staticmethod
    def load_request(path: Path | None = None) -> str:
        p = path or REQUEST_PATH
        return p.read_text(encoding="utf-8") if p.exists() else ""

    @staticmethod
    def load_contract(path: Path | None = None) -> str:
        p = path or CONTRACT_PATH
        return p.read_text(encoding="utf-8") if p.exists() else ""
