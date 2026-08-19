"""探索予算（explore / exploit）の制御。

GPT からの指摘（採用）: 「収益実績のあるキーワードに +5」は、勝っている市場ばかり
再発見するフィードバックループを作り、本来の目的（まだ見つかっていない次の市場を
探す）能力を落とす。加点は削除し、代わりに **調査枠を予算として分ける**。

  exploit 枠: 既に採用済みのニッチと関連する候補（深掘り）
  explore 枠: 採用済みニッチと語がまったく重ならない候補（新規開拓）

初期は採用ニッチが0件なので全枠が自動的に explore になる。枠が意味を持つのは
実績が溜まってから。つまり「早く始める」ことを邪魔しない。
"""
from __future__ import annotations

import logging

from .models import Candidate, normalize_tokens

logger = logging.getLogger(__name__)


# 実績の状態に応じた explore 枠。固定比率にしない（GPT提案⑤を採用）。
# 勝ちパターンが無いうちは探索するしかなく、安定収益源ができたら深掘りに寄せる。
EXPLORE_LADDER = (
    (0, 1.00),        # winner 0件 → 全部 explore
    (1, 0.30),        # 初売上が出た → 30%
    (3, 0.20),        # 勝ちパターンが複数 → 20%
    (5, 0.15),        # 安定した収益源あり → 15%
)


def explore_ratio_for(winners: int, fallback: float = 0.2) -> float:
    """勝っているニッチの数から explore 枠の割合を決める。"""
    ratio = fallback
    for threshold, value in EXPLORE_LADDER:
        if winners >= threshold:
            ratio = value
    return ratio


def split_by_novelty(candidates: list[tuple[Candidate, int]],
                     adopted_texts: list[str]) -> tuple[list, list]:
    """(exploit候補, explore候補) に分ける。

    採用済みニッチの語と1語でも重なれば exploit、まったく重ならなければ explore。
    """
    adopted_tokens = normalize_tokens(*adopted_texts)
    if not adopted_tokens:
        return [], list(candidates)

    exploit, explore = [], []
    for pair in candidates:
        candidate = pair[0]
        tokens = normalize_tokens(candidate.title, " ".join(candidate.keywords))
        (exploit if tokens & adopted_tokens else explore).append(pair)
    return exploit, explore


def allocate(candidates: list[tuple[Candidate, int]], adopted_texts: list[str],
             total_slots: int, explore_ratio: float = 0.2,
             winners: int | None = None) -> list[tuple[Candidate, int]]:
    """調査枠を exploit / explore に配分して候補を選ぶ。

    `winners`（実際に収益が出たニッチ数）を渡すと、比率を状態から決める。
    枠が埋まらない側の余りはもう一方に回す（枠を守るために調査数を減らさない）。
    """
    if total_slots <= 0:
        return []

    if winners is not None:
        explore_ratio = explore_ratio_for(winners, explore_ratio)

    exploit, explore = split_by_novelty(candidates, adopted_texts)
    if not exploit:
        return explore[:total_slots]

    explore_slots = max(1, round(total_slots * explore_ratio))
    exploit_slots = total_slots - explore_slots

    picked = exploit[:exploit_slots] + explore[:explore_slots]

    # 片側が足りなければもう一方で埋める
    if len(picked) < total_slots:
        remaining = [c for c in exploit[exploit_slots:] + explore[explore_slots:]
                     if c not in picked]
        picked += remaining[: total_slots - len(picked)]

    logger.info("調査枠の配分: exploit %d件 / explore %d件（explore_ratio=%.2f）",
                sum(1 for p in picked if p in exploit),
                sum(1 for p in picked if p in explore), explore_ratio)
    return picked[:total_slots]
