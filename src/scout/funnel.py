"""ファネル段階による撤退判定。

GPT からの指摘（採用）: 「30日で収益0なら撤退」は単純すぎる。
100インプで0円と10万インプで0円は全く違う。判断は **時間ではなく十分な試行回数**
を基準にし、どこで詰まったかを段階で切り分ける。

  Stage 1 配信されない      → テーマかフォーマットの問題（ニッチが悪い）
  Stage 2 見られるが反応なし → コンテンツか切り口の問題（動画が悪い）
  Stage 3 反応はあるがCTR低  → オファーとの接続が弱い（導線が悪い）
  Stage 4 CTRは良いがCVなし  → 商品・LP・案件選定の問題（商品が悪い）

実装上の制約: これらの指標（インプ・視聴維持・CTR・CV）は TikTok / YouTube /
ASP の管理画面にしかない。API 連携は審査が必要で初売上前には重い。
そこで MVP は **`/metrics` コマンドで週1回スマホから手入力**する形にした。
30秒で済み、Stage 1 と Stage 2 の切り分けは即座にできるようになる。

閾値 N は本来「既存パイプラインの実績分布から決める」べきだが、実績が0件の時点では
分布が無い。保守的な既定値を置き、実績が溜まったら config で上げる。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

STAGES = {
    1: ("配信されない", "テーマかフォーマットの問題。ニッチを変える"),
    2: ("見られるが反応されない", "コンテンツか切り口の問題。フックを変える"),
    3: ("反応はあるがクリックされない", "オファーとの接続が弱い。CTAを変える"),
    4: ("クリックされるが売れない", "商品・案件選定の問題。案件を変える"),
    5: ("売れている", "継続。この構成を他ニッチにも適用する"),
}


@dataclass
class FunnelMetrics:
    """1ニッチ分の実績。`/metrics` で手入力するか、将来 API で自動取得する。"""

    niche: str
    posts: int = 0
    impressions: int = 0
    engaged: int = 0          # 視聴完了 / 保存など反応した数
    cta_clicks: int = 0
    conversions: int = 0
    revenue_jpy: int = 0
    attention_minutes: float = 0.0   # 人間がこのニッチに使った判断時間
    api_cost_jpy: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    # --- 露出量で正規化した指標（累計売上では判断しない） ---
    @property
    def engagement_rate(self) -> float:
        return self.engaged / self.impressions if self.impressions else 0.0

    @property
    def ctr(self) -> float:
        return self.cta_clicks / self.impressions if self.impressions else 0.0

    @property
    def cvr(self) -> float:
        return self.conversions / self.cta_clicks if self.cta_clicks else 0.0

    @property
    def epc(self) -> float:
        """クリック単価。案件の良さを露出量に依存せず見る指標。"""
        return self.revenue_jpy / self.cta_clicks if self.cta_clicks else 0.0

    @property
    def rpm(self) -> float:
        """1,000インプあたり収益。ニッチ間の比較はこれで行う。"""
        return self.revenue_jpy / self.impressions * 1000 if self.impressions else 0.0

    @property
    def revenue_per_attention_minute(self) -> float:
        """人間の判断1分あたりの収益。最終的な目的関数の実測値。"""
        return self.revenue_jpy / self.attention_minutes if self.attention_minutes else 0.0

    @property
    def profit_jpy(self) -> int:
        return self.revenue_jpy - self.api_cost_jpy


@dataclass
class FunnelVerdict:
    stage: int
    label: str
    prescription: str
    decided: bool               # 十分な試行回数に達したか
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    @property
    def should_exit(self) -> bool:
        """撤退すべきか。試行回数が足りていなければ常に False。"""
        return self.decided and self.stage == 1

    def to_dict(self) -> dict:
        return asdict(self)


class FunnelDiagnoser:
    def __init__(self, thresholds: dict | None = None):
        t = thresholds or {}
        # 「十分な試行回数」の定義。時間ではなくこれで判定する。
        self.min_posts = int(t.get("min_posts", 8))
        self.min_impressions = int(t.get("min_impressions", 2000))
        # 各段階の合格ライン
        self.min_impressions_per_post = float(t.get("min_impressions_per_post", 150))
        self.min_engagement_rate = float(t.get("min_engagement_rate", 0.02))
        self.min_ctr = float(t.get("min_ctr", 0.005))
        self.min_conversions = int(t.get("min_conversions", 1))

    def diagnose(self, m: FunnelMetrics) -> FunnelVerdict:
        """どこで詰まっているかを判定する。"""
        decided = m.posts >= self.min_posts or m.impressions >= self.min_impressions
        reason = (f"投稿{m.posts}本 / インプ{m.impressions:,}"
                  f"（判定に必要: {self.min_posts}本 または {self.min_impressions:,}インプ）")

        stage = self._stage(m)
        label, prescription = STAGES[stage]
        if not decided:
            prescription = f"まだ判定しない。{prescription}（試行回数が不足）"

        return FunnelVerdict(stage=stage, label=label, prescription=prescription,
                             decided=decided, reason=reason,
                             metrics={"impressions_per_post": self._per_post(m),
                                      "engagement_rate": round(m.engagement_rate, 4),
                                      "ctr": round(m.ctr, 4), "cvr": round(m.cvr, 4),
                                      "epc": round(m.epc, 1), "rpm": round(m.rpm, 1),
                                      "revenue_per_attention_minute":
                                          round(m.revenue_per_attention_minute, 1)})

    def _stage(self, m: FunnelMetrics) -> int:
        if self._per_post(m) < self.min_impressions_per_post:
            return 1
        if m.engagement_rate < self.min_engagement_rate:
            return 2
        if m.ctr < self.min_ctr:
            return 3
        if m.conversions < self.min_conversions:
            return 4
        return 5

    @staticmethod
    def _per_post(m: FunnelMetrics) -> float:
        return m.impressions / m.posts if m.posts else 0.0
