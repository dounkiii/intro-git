"""設計レビューの自動化。

`docs/REVIEW_REQUEST.md` を LLM に投げ、指摘を GitHub Issue にコメントする。
オーナーが ChatGPT へコピペする作業をなくすためのもの。

**このレビュワーは「同意する係」ではない。** 相手が LLM なので、放っておくと
「妥当だと思います」しか返らない。それはレビューではなくノイズなので、

  - 出力を構造化して**具体的な指摘を必須**にする（agree だけを返せない）
  - 凍結契約を渡し、**凍結対象への変更提案は却下対象**として扱わせる
  - 同意しかない回を記録し、続くようならレビュー自体をやめる材料にする

を仕込んである。詳細は `Critic` の docstring。
"""
from .critic import Critic, CritiqueResult

__all__ = ["Critic", "CritiqueResult"]
