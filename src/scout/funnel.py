"""ファネル段階による撤退判定。

方針: 撤退は「30日で収益0」ではなく **十分な試行回数に達したあと、どこで詰まったか**
で判断する。100インプで0円と10万インプで0円は全く違う。

  Stage 0 判定不能            → 指標が入っていない。UNKNOWN のまま前に進める
  Stage 1 配信されない        → 配信の失敗。**原因はまだ断定しない**
  Stage 2 見られるが反応なし  → コンテンツか切り口の問題
  Stage 3 反応はあるがCTR低   → オファーとの接続が弱い
  Stage 4 CTRは良いがCVなし   → 商品・LP・案件選定の問題
  Stage 5 売れている          → 継続

**Stage は症状の診断であり、原因の断定ではない。** GPT からの指摘（採用）:
10投稿で平均100 views だとしても、原因はニッチ・フック・構成・投稿時間・
アカウント状態・プラットフォーム相性・クリエイティブ品質が混ざっている。
Stage 1 を「ニッチ失敗」と読むと良いニッチを捨てる。そこで

  - Stage 1 の名前を DISTRIBUTION_FAILURE（配信の失敗）にした
  - ニッチ撤退の推奨には **同ニッチ × 複数クリエイティブ** または
    **同フォーマット × 他ニッチとの比較** を要求する（`likely_cause`）

GPT との議論を経て入れた3点:

1. **Stage 0（判定不能）を明示する。** views が未入力のとき Stage 1 と Stage 4 は
   区別できない。区別できないものを「Stage 1 = ニッチが悪い」と診断すると、
   良いニッチを誤って捨てる。UNKNOWN と言い切る方が安全。

2. **Core / Diagnostic の分離。** 初売上の確認に必要なのは posts / views / revenue の
   3つだけ。clicks・CTR・CVR は「売れなかった原因を調べる」ときに必要になるもので、
   最初から要求すると入力が続かず台帳が育たない。完璧な台帳より続く台帳。

3. **絶対値のベンチマークを信用しすぎない。** 判定は
   自アカウントの実績中央値 → プラットフォーム既定 → 絶対値の仮値
   の順にフォールバックする。世間の平均より自分の通常成績の方が価値が高い。
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

STAGES = {
    0: ("判定不能", "指標が未入力。views か revenue を入れると診断できる"),
    1: ("配信の失敗", "配信されていない。原因は切り口かニッチか、まだ切り分けられていない"),
    2: ("見られるが反応されない", "コンテンツか切り口の問題。フックを変える"),
    3: ("反応はあるがクリックされない", "オファーとの接続が弱い。CTAを変える"),
    4: ("クリックされるが売れない", "商品・案件選定の問題。案件を変える"),
    5: ("売れている", "継続。この構成を他ニッチにも適用する"),
}

# 原因の推定。Stage（症状）とは別に持ち、断定できないときは unknown にする。
CAUSE_UNKNOWN = "unknown"
CAUSE_CREATIVE = "creative"       # 切り口・クリエイティブが原因の可能性が高い
CAUSE_NICHE = "niche"             # ニッチ自体が原因の可能性が高い
CAUSE_FUNNEL = "funnel"           # 導線・CTA
CAUSE_OFFER = "offer"             # 商品・案件
# 直接の換金経路がまだ無い。案件の良し悪しは判定不能（Stage 0 と同じ思想）
CAUSE_NOT_MONETIZED = "not_monetized"

# 同ニッチで最低これだけ切り口を変えないと、ニッチ原因とは言わない
MIN_CREATIVES_FOR_NICHE_CAUSE = 2
# 同フォーマットの他ニッチ中央値に対してこの比率を下回れば、ニッチ側が疑わしい
NICHE_UNDERPERFORM_RATIO = 0.3

# プラットフォームごとの既定しきい値。絶対基準ではなく初期仮説。
# 自アカウントの実績中央値が取れたらそちらを優先する。
PLATFORM_DEFAULTS = {
    "tiktok": {"min_posts": 8, "min_impressions": 2000,
               "min_impressions_per_post": 150, "min_engagement_rate": 0.02,
               "min_ctr": 0.005},
    # Shorts は「サムネイル表示回数」と「実際に見られた回数」の差が大きいので
    # 1投稿あたりの下限を高く、反応率の下限を低く置く。
    "youtube_shorts": {"min_posts": 8, "min_impressions": 3000,
                       "min_impressions_per_post": 250, "min_engagement_rate": 0.01,
                       "min_ctr": 0.004},
    # X はインプが出やすくクリックが取りにくい。
    "x": {"min_posts": 15, "min_impressions": 5000,
          "min_impressions_per_post": 300, "min_engagement_rate": 0.01,
          "min_ctr": 0.003},
}
DEFAULT_PLATFORM = "tiktok"

# 自アカウントの中央値に対する比率で「配信されていない」を判定する。
BASELINE_FAILURE_RATIO = 0.3
BASELINE_STRONG_RATIO = 1.5
BASELINE_MIN_SAMPLES = 10


@dataclass
class FunnelMetrics:
    """1ニッチ分の実績。

    Core（posts / impressions / revenue）だけで Stage 判定は成立する。
    Diagnostic（engaged / cta_clicks / conversions）は取れたときだけ入れる。
    """

    niche: str
    platform: str = DEFAULT_PLATFORM

    # --- Core ---
    posts: int = 0
    impressions: int | None = None     # None = 未入力（0 と区別する）
    revenue_jpy: int = 0
    # 直接の換金経路（AFF_* の案件）が実在するか。None = 未記録。
    # False の期間はクリックが出ても成約は起こり得ないので、収益0を
    # 「案件が悪い」とも「このニッチは売れない」とも読まない。
    direct_route: bool | None = None

    # --- Diagnostic（任意） ---
    engaged: int | None = None
    cta_clicks: int | None = None
    conversions: int | None = None

    attention_minutes: float = 0.0     # 人間がこのニッチに使った判断時間
    api_cost_jpy: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def has_core(self) -> bool:
        """Stage 判定に足りる最低限の情報があるか。

        必要なのは impressions だけ。posts は1投稿あたりに正規化するためのもので、
        自前ログから自動で埋まるが、埋まらなくても総インプで判定できる。
        """
        return self.impressions is not None

    # --- 露出量で正規化した指標（累計売上では判断しない） ---
    @property
    def impressions_per_post(self) -> float:
        if not self.posts or self.impressions is None:
            return 0.0
        return self.impressions / self.posts

    @property
    def engagement_rate(self) -> float | None:
        if self.engaged is None or not self.impressions:
            return None
        return self.engaged / self.impressions

    @property
    def ctr(self) -> float | None:
        if self.cta_clicks is None or not self.impressions:
            return None
        return self.cta_clicks / self.impressions

    @property
    def cvr(self) -> float | None:
        if self.conversions is None or not self.cta_clicks:
            return None
        return self.conversions / self.cta_clicks

    @property
    def epc(self) -> float | None:
        if not self.cta_clicks:
            return None
        return self.revenue_jpy / self.cta_clicks

    @property
    def rpm(self) -> float:
        """1,000インプあたり収益。ニッチ間の比較はこれで行う。"""
        if not self.impressions:
            return 0.0
        return self.revenue_jpy / self.impressions * 1000

    @property
    def revenue_per_post(self) -> float:
        return self.revenue_jpy / self.posts if self.posts else 0.0

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
    decided: bool                       # 十分な試行回数に達したか
    reason: str = ""
    basis: str = "platform_default"     # own_baseline | platform_default
    likely_cause: str = CAUSE_UNKNOWN   # 原因の推定。断定できなければ unknown
    cause_reason: str = ""
    metrics: dict = field(default_factory=dict)

    @property
    def should_exit(self) -> bool:
        """ニッチを捨てるべきか。

        Stage 1（配信の失敗）だけでは撤退させない。原因がニッチ側だと
        言えるだけの比較材料（複数クリエイティブ or 他ニッチとの差）が要る。
        """
        return self.decided and self.stage == 1 and self.likely_cause == CAUSE_NICHE

    @property
    def retry_creative(self) -> bool:
        """切り口を変えて再試行すべきか。"""
        return self.decided and self.stage == 1 and self.likely_cause == CAUSE_CREATIVE

    def to_dict(self) -> dict:
        return asdict(self)


class FunnelDiagnoser:
    def __init__(self, thresholds: dict | None = None,
                 platform: str = DEFAULT_PLATFORM,
                 baseline_samples: list[float] | None = None,
                 peer_samples: dict[str, float] | None = None):
        """`baseline_samples` は自アカウントの「1投稿あたりインプ」の実績列。

        10件以上あれば、その中央値を基準に「配信されていない」を判定する
        （世間一般の平均より自分の通常成績の方が判断材料として強い）。
        """
        base = dict(PLATFORM_DEFAULTS.get(platform, PLATFORM_DEFAULTS[DEFAULT_PLATFORM]))
        base.update({k: v for k, v in (thresholds or {}).items() if v is not None})

        self.platform = platform
        self.min_posts = int(base.get("min_posts", 8))
        self.min_impressions = int(base.get("min_impressions", 2000))
        self.min_impressions_per_post = float(base.get("min_impressions_per_post", 150))
        self.min_engagement_rate = float(base.get("min_engagement_rate", 0.02))
        self.min_ctr = float(base.get("min_ctr", 0.005))
        self.min_conversions = int(base.get("min_conversions", 1))
        self.baseline_samples = [s for s in (baseline_samples or []) if s > 0]
        # {niche_slug: 1投稿あたりインプ}。同フォーマットの他ニッチとの比較に使う。
        self.peer_samples = {k: v for k, v in (peer_samples or {}).items() if v > 0}

    # ------------------------------------------------------------------
    @property
    def baseline(self) -> float | None:
        """自アカウントの1投稿あたりインプの中央値。サンプル不足なら None。"""
        if len(self.baseline_samples) < BASELINE_MIN_SAMPLES:
            return None
        return statistics.median(self.baseline_samples)

    def distribution_floor(self) -> tuple[float, str]:
        """「配信されていない」の判定ライン。自分の実績があればそれを優先する。"""
        baseline = self.baseline
        if baseline is not None:
            return baseline * BASELINE_FAILURE_RATIO, "own_baseline"
        return self.min_impressions_per_post, "platform_default"

    def diagnose(self, m: FunnelMetrics, creatives_tried: int = 1) -> FunnelVerdict:
        floor, basis = self.distribution_floor()

        if not m.has_core:
            label, prescription = STAGES[0]
            return FunnelVerdict(
                stage=0, label=label, prescription=prescription, decided=False,
                reason=f"views が未入力。収益 {m.revenue_jpy:,}円 は記録済み"
                       f"（UNKNOWN のまま進めます）",
                basis=basis, metrics=self._metrics(m, floor),
            )

        decided = m.posts >= self.min_posts or (m.impressions or 0) >= self.min_impressions
        stage = self._stage(m, floor)
        label, prescription = STAGES[stage]
        cause, cause_reason = self._cause(m, stage, creatives_tried)
        if not decided:
            prescription = f"まだ判定しない。{prescription}（試行回数が不足）"
        elif stage == 1:
            prescription = ("切り口を変えてもう一度試す" if cause == CAUSE_CREATIVE
                            else "ニッチ側が原因の可能性が高い。撤退を検討する"
                            if cause == CAUSE_NICHE else prescription)
        elif cause == CAUSE_NOT_MONETIZED:
            # 既定の「案件を変える」は、変える案件が無いので実行できない
            prescription = ("直接の換金経路が未提携。案件を変えるのではなく "
                            "提携申請を通す（オーナー側の作業）")

        basis_note = ("自アカウントの実績中央値" if basis == "own_baseline"
                      else f"{self.platform} の既定値")
        return FunnelVerdict(
            stage=stage, label=label, prescription=prescription, decided=decided,
            reason=f"投稿{m.posts or '?'}本 / インプ{(m.impressions or 0):,}"
                   f"（判定に必要: {self.min_posts}本 または {self.min_impressions:,}インプ）"
                   f"／配信の下限は{basis_note} {floor:.0f}",
            basis=basis, likely_cause=cause, cause_reason=cause_reason,
            metrics=self._metrics(m, floor),
        )

    def _cause(self, m: FunnelMetrics, stage: int,
               creatives_tried: int) -> tuple[str, str]:
        """原因を推定する。断定できないときは unknown を返す。"""
        if stage in (0, 5):
            return CAUSE_UNKNOWN, ""
        if stage == 2:
            return CAUSE_CREATIVE, "配信はされているが反応がない"
        if stage == 3:
            return CAUSE_FUNNEL, "反応はあるがクリックされていない"
        if stage == 4:
            if m.direct_route is False:
                return CAUSE_NOT_MONETIZED, (
                    "クリックは出ているが直接の換金経路が未提携。"
                    "案件の良し悪しはまだ判定できない")
            return CAUSE_OFFER, "クリックはあるが成約していない"

        # Stage 1: ここが断定してはいけない箇所
        if creatives_tried < MIN_CREATIVES_FOR_NICHE_CAUSE:
            return CAUSE_CREATIVE, (
                f"試した切り口が {creatives_tried} 種類。ニッチ原因と言うには "
                f"{MIN_CREATIVES_FOR_NICHE_CAUSE} 種類以上を同じニッチで試す必要がある")

        peers = [v for slug, v in self.peer_samples.items() if slug != m.niche]
        if peers:
            peer_median = statistics.median(peers)
            if m.impressions_per_post < peer_median * NICHE_UNDERPERFORM_RATIO:
                return CAUSE_NICHE, (
                    f"同フォーマットの他ニッチ中央値 {peer_median:.0f} に対して "
                    f"{m.impressions_per_post:.0f}。ニッチ側が疑わしい")
            return CAUSE_CREATIVE, (
                f"他ニッチ中央値 {peer_median:.0f} と大きく変わらないので、"
                f"ニッチではなく制作側を疑う")

        return CAUSE_NICHE, (
            f"{creatives_tried} 種類の切り口で配信されなかった"
            f"（他ニッチとの比較材料はまだ無い）")

    def _stage(self, m: FunnelMetrics, floor: float) -> int:
        if not self._distribution_ok(m, floor):
            return 1
        # Diagnostic が無い場合は、その段階を飛ばして判断できるところまで進む。
        # 「取れていない」を「悪い」と読み替えないため。
        if m.engagement_rate is not None and m.engagement_rate < self.min_engagement_rate:
            return 2
        if m.ctr is not None and m.ctr < self.min_ctr:
            return 3
        if m.revenue_jpy > 0:
            return 5
        if m.conversions is not None and m.conversions < self.min_conversions:
            return 4
        if m.cta_clicks is None and m.engaged is None:
            # 配信はされているが、反応も売上も分からない
            return 0
        return 4

    def _distribution_ok(self, m: FunnelMetrics, floor: float) -> bool:
        """配信されているか。

        posts が分かるなら1投稿あたりで見る（本数の差を吸収できる）。
        分からないときは総インプで見る（posts 未取得を「配信失敗」と誤診しないため）。
        """
        if m.posts > 0:
            return m.impressions_per_post >= floor
        return (m.impressions or 0) >= self.min_impressions

    def _metrics(self, m: FunnelMetrics, floor: float) -> dict:
        def opt(v, digits=4):
            return round(v, digits) if v is not None else None

        return {
            "impressions_per_post": round(m.impressions_per_post, 1),
            "distribution_floor": round(floor, 1),
            "engagement_rate": opt(m.engagement_rate),
            "ctr": opt(m.ctr), "cvr": opt(m.cvr),
            "epc": opt(m.epc, 1), "rpm": round(m.rpm, 1),
            "revenue_per_post": round(m.revenue_per_post, 1),
            "revenue_per_attention_minute": round(m.revenue_per_attention_minute, 1),
        }
