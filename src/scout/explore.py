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
             total_slots: int, explore_ratio: float = 0.2) -> list[tuple[Candidate, int]]:
    """調査枠を exploit / explore に配分して候補を選ぶ。

    枠が埋まらない側の余りはもう一方に回す（枠を守るために調査数を減らさない）。
    """
    if total_slots <= 0:
        return []

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
