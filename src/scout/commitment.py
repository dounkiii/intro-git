"""投資レベル（commitment level）— 分類と「いくら賭けるか」を分離する。

GPT からの指摘（採用）: confidence を順位から外しても、`now` 判定のゲートに使う限り
「早い → データが少ない → confidence 低 → 実行されない」が残る。
本当に欲しいのは「確信してから大きく賭ける」ことではなく
**「不確実だが期待値の高いものを安く試す」**こと。

そこで verdict（症状の分類: drop/watch/now）と commitment（投資レベル）を分けた。
confidence は「やる/やらない」ではなく **いくら賭けるか** を決める変数になる。

  OBSERVE     何もしない。監視のみ
  CHEAP_TEST  機会は高いが根拠が薄い → 最小本数だけ作って実データを取る
  ADOPT       根拠が揃った → 通常の制作パイプラインへ
  SCALE       実績が出た → 生成枠を増やす
  EXIT        十分試してダメだった

ラベルだけでは意味がないので、各レベルに **1回の生成で作る本数の上限** を持たせ、
実績（ファネル段階）から自動で遷移させる。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

OBSERVE = "OBSERVE"
CHEAP_TEST = "CHEAP_TEST"
ADOPT = "ADOPT"
SCALE = "SCALE"
EXIT = "EXIT"

LEVELS = (OBSERVE, CHEAP_TEST, ADOPT, SCALE, EXIT)

LABELS = {
    OBSERVE: "監視のみ",
    CHEAP_TEST: "小さく試す",
    ADOPT: "通常運用",
    SCALE: "増やす",
    EXIT: "撤退",
}


@dataclass(frozen=True)
class Budget:
    """そのレベルで許す投資量。"""

    items_per_run: int      # 1回の生成で作る本数の上限
    test_posts: int         # このレベルで公開する上限（0 = 上限なし）

    def to_dict(self) -> dict:
        return {"items_per_run": self.items_per_run, "test_posts": self.test_posts}


# CHEAP_TEST の上限を小さくしているのが要点。外れても損失が小さいので、
# 確信が持てない候補を「様子見」で放置せず、実データを取りに行ける。
BUDGETS = {
    OBSERVE: Budget(items_per_run=0, test_posts=0),
    CHEAP_TEST: Budget(items_per_run=1, test_posts=3),
    ADOPT: Budget(items_per_run=2, test_posts=0),
    SCALE: Budget(items_per_run=4, test_posts=0),
    EXIT: Budget(items_per_run=0, test_posts=0),
}


def budget_for(level: str) -> Budget:
    return BUDGETS.get(level, BUDGETS[OBSERVE])


def initial_level(verdict: str, confidence: float, opportunity: float,
                  now_confidence: float = 0.45, min_test_opportunity: float = 20.0) -> str:
    """探索結果から最初の投資レベルを決める。

    `now` 相当だが確信が低いものを watch に落とさず CHEAP_TEST に送るのが目的。
    ここが「高Opportunity × 低Confidence を watch している間に他者に取られる」を防ぐ。
    """
    if verdict == "drop":
        return OBSERVE
    if opportunity < min_test_opportunity:
        return OBSERVE
    if confidence >= now_confidence:
        return ADOPT if verdict == "now" else CHEAP_TEST
    # 確信が低い = 小さく試して実データを取る
    return CHEAP_TEST


def next_level(current: str, stage: int, decided: bool, revenue_jpy: int,
               posts: int, creatives_tried: int,
               min_creatives_before_exit: int = 2) -> tuple[str, str]:
    """実績から次の投資レベルを決める。(次のレベル, 理由) を返す。

    遷移は実測ベースで、推測では動かさない。判定不能（Stage 0）や試行不足では
    レベルを動かさない（データが無いことを「悪い」と読み替えない）。
    """
    if current in (OBSERVE, EXIT):
        return current, "レベル変更なし"

    if revenue_jpy > 0:
        if current != SCALE:
            return SCALE, f"売上 {revenue_jpy:,}円 が出たので生成枠を増やす"
        return SCALE, "売上継続。この構成を維持"

    if stage == 0 or not decided:
        return current, "実績が不足しているためレベルは変更しない"

    if stage == 1:
        # 配信されていない。ただし1本のクリエイティブで断定はしない。
        if creatives_tried < min_creatives_before_exit:
            return CHEAP_TEST, (f"配信されていないが試したクリエイティブが "
                                f"{creatives_tried}種類。切り口を変えてもう一度試す")
        return EXIT, (f"{creatives_tried}種類のクリエイティブで配信されなかったため撤退")

    # 配信はされている（Stage 2〜4）。原因はニッチではないので本運用に上げて調べる。
    if current == CHEAP_TEST:
        return ADOPT, f"配信は成立している（Stage {stage}）ので通常運用に上げる"
    return current, f"Stage {stage} の改善に取り組む（レベルは維持）"
