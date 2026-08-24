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
  SCALE       **再現性が確認できた** → 生成枠を増やす
  EXIT        十分試してダメだった

昇格には2つの歯止めを置いている。

1. **「売れた」と「再現性がある」を分ける。** 1件の売上は偶然の可能性があるので、
   初回売上では SCALE にせず ADOPT に留める。CV 2件以上、または売上が2回以上
   観測されて初めて SCALE にする。初回の成功シグナルへの過剰反応を防ぐため。

2. **「配信は成立している」と「制作量を増やすべき」を分ける。** Stage 2〜4 は
   配信されているのでニッチ撤退はしないが、原因（切り口 / 導線 / 案件）が
   解消されていない状態で本数を増やすと、**悪い導線に対して制作量だけ増える**。
   診断中フラグ（`diagnosing`）を立て、その間は生成枠を増やさない。

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


# 診断中（Stage 2〜4 の原因が未解消）のあいだ許す本数。レベルに関わらずここまで。
DIAGNOSING_ITEMS_PER_RUN = 1

# SCALE に上げるための再現性の条件（いずれかを満たせばよい）。仮値。
MIN_CONVERSIONS_FOR_SCALE = 2
MIN_REVENUE_EVENTS_FOR_SCALE = 2

# 診断中を示す原因ラベル（funnel.py の CAUSE_* と対応）
DIAGNOSING_CAUSES = ("creative", "funnel", "offer")

# 直接の換金経路が無い期間。診断中には入れない（原因はニッチ側に無い）
CAUSE_NOT_MONETIZED = "not_monetized"

# CHEAP_TEST の上限を小さくしているのが要点。外れても損失が小さいので、
# 確信が持てない候補を「様子見」で放置せず、実データを取りに行ける。
BUDGETS = {
    OBSERVE: Budget(items_per_run=0, test_posts=0),
    CHEAP_TEST: Budget(items_per_run=1, test_posts=3),
    ADOPT: Budget(items_per_run=2, test_posts=0),
    SCALE: Budget(items_per_run=4, test_posts=0),
    EXIT: Budget(items_per_run=0, test_posts=0),
}


def budget_for(level: str, diagnosing: str = "") -> Budget:
    """レベルに対応する予算。診断中は生成枠を増やさない。

    Stage 2〜4 の原因が未解消のまま本数を増やすと、悪い導線に対して制作量だけ
    増やすことになる。診断が終わるまで枠を絞る。
    """
    budget = BUDGETS.get(level, BUDGETS[OBSERVE])
    if diagnosing and budget.items_per_run > DIAGNOSING_ITEMS_PER_RUN:
        return Budget(items_per_run=DIAGNOSING_ITEMS_PER_RUN,
                      test_posts=budget.test_posts)
    return budget


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


def is_reproducible(conversions: int | None, revenue_events: int,
                    min_conversions: int = MIN_CONVERSIONS_FOR_SCALE,
                    min_revenue_events: int = MIN_REVENUE_EVENTS_FOR_SCALE
                    ) -> tuple[bool, str]:
    """売上に再現性があるか。「売れた」と「再現性がある」を分けるための判定。

    `revenue_events` は売上が増えたことを観測した回数（Ledger から数える）。
    CV が取れないプラットフォームでも判定できるよう、2つの条件のどちらかで通す。
    閾値は仮値で、実績が溜まったら `config.yaml` の `scout.scale_gate` で見直す。
    """
    if conversions is not None and conversions >= min_conversions:
        return True, f"CV {conversions}件（{min_conversions}件以上）"
    if revenue_events >= min_revenue_events:
        return True, f"売上を{revenue_events}回観測（{min_revenue_events}回以上）"
    detail = (f"CV {conversions if conversions is not None else '不明'}件 / "
              f"売上観測 {revenue_events}回")
    return False, detail


def next_level(current: str, stage: int, decided: bool, revenue_jpy: int,
               posts: int, creatives_tried: int,
               min_creatives_before_exit: int = 2,
               conversions: int | None = None, revenue_events: int = 0,
               likely_cause: str = "",
               scale_gate: dict | None = None) -> tuple[str, str, str]:
    """実績から次の投資レベルを決める。(次のレベル, 理由, 診断中の原因) を返す。

    遷移は実測ベースで、推測では動かさない。判定不能（Stage 0）や試行不足では
    レベルを動かさない（データが無いことを「悪い」と読み替えない）。
    """
    if current in (OBSERVE, EXIT):
        return current, "レベル変更なし", ""

    if revenue_jpy > 0:
        gate = scale_gate or {}
        reproducible, detail = is_reproducible(
            conversions, revenue_events,
            min_conversions=int(gate.get("min_conversions", MIN_CONVERSIONS_FOR_SCALE)),
            min_revenue_events=int(gate.get("min_revenue_events",
                                            MIN_REVENUE_EVENTS_FOR_SCALE)))
        if reproducible:
            if current != SCALE:
                return SCALE, f"再現性を確認（{detail}）したので生成枠を増やす", ""
            return SCALE, f"売上継続（{detail}）。この構成を維持", ""
        # 初回売上は偶然の可能性がある。通常運用までは上げるが SCALE にはしない。
        target = ADOPT if current == CHEAP_TEST else current
        return target, (f"売上 {revenue_jpy:,}円 が出たが再現性が未確認（{detail}）。"
                        f"SCALE にはせず {target} で継続する"), ""

    if stage == 0 or not decided:
        return current, "実績が不足しているためレベルは変更しない", ""

    if stage == 1:
        # 配信されていない。ただし1本のクリエイティブで断定はしない。
        if creatives_tried < min_creatives_before_exit:
            return CHEAP_TEST, (f"配信されていないが試したクリエイティブが "
                                f"{creatives_tried}種類。切り口を変えてもう一度試す"), ""
        return EXIT, (f"{creatives_tried}種類のクリエイティブで配信されなかったため撤退"), ""

    # 直接の換金経路が未提携なら、成約しないのは案件のせいではない。
    # 診断中にして生成枠を絞ると、配信もクリックも成立している唯一のニッチを
    # オーナー側の作業待ちで減速させることになる。レベルは動かさない。
    if likely_cause == CAUSE_NOT_MONETIZED:
        return current, (f"配信もクリックは成立している（Stage {stage}）が、"
                         f"直接の換金経路が未提携。案件の良し悪しは判定不能なので "
                         f"レベルは動かさない（提携が通ってから評価する）"), ""

    # Stage 2〜4: 配信は成立しているのでニッチ撤退はしない。
    # ただし原因が解消されていないので生成枠は増やさない（診断中）。
    cause = likely_cause if likely_cause in DIAGNOSING_CAUSES else "creative"
    label = {"creative": "切り口", "funnel": "導線・CTA", "offer": "案件・商品"}[cause]
    return current, (f"配信は成立している（Stage {stage}）が {label} が未解消。"
                     f"診断中は生成枠を増やさない"), cause
