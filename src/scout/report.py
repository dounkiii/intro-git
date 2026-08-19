"""日次レポート。ちゃっぴー案の出力フォーマットをほぼそのまま採用している。

大量に見せず上位だけ出す方針も同じ。ただし 2 点足した。
  - 「LLMと実測の矛盾」を明示する（鵜呑みにさせないため）
  - `/adopt <id>` ボタンを付けて、そのまま制作パイプラインへ流せるようにした
    （発掘だけして何も作られない、という情報収集システムの典型的な死に方を防ぐ）
"""
from __future__ import annotations

from .models import Opportunity

VERDICT_LABEL = {"now": "🔥 今すぐ狙う", "watch": "👀 様子見", "drop": "🗑 捨てる"}


def _bullets(values: list[str], empty: str = "（なし）") -> str:
    return "\n".join(f"- {v}" for v in values) if values else f"- {empty}"


def render_opportunity(opportunity: Opportunity, rank: int) -> str:
    c, r, s = opportunity.candidate, opportunity.research, opportunity.score
    heading = "今日の1位" if rank == 1 else f"第{rank}位"

    lines = [
        f"## {heading}　{VERDICT_LABEL.get(opportunity.verdict, opportunity.verdict)}",
        "",
        f"**ネタ**: {c.title}",
        f"**概要**: {c.summary or '（なし）'}",
        f"**なぜ今なのか**: {r.why_now or '不明'}",
        f"**想定ユーザー**: {r.target_user or '不明'}",
        "",
        "**収益化方法**",
        _bullets(r.monetization_paths, "未検討"),
        "",
        f"**最もおすすめの商品・コンテンツ**: {r.best_product or '未検討'}",
        f"**競合状況**: {r.competitor_note or '不明'}"
        f"（実測: 独立ドメイン {r.measured.get('competitor_domains', 0)}件 /"
        f" 根拠URL {r.measured.get('evidence_count', 0)}件）",
        "",
        "**リスク**",
        _bullets(r.risks, "特になし"),
        "",
        f"**機会スコア**: {s.opportunity}/100　"
        f"**確信度**: {s.confidence:.2f}"
        + ("　🎲 スコアは高いが根拠が薄い（explore 向き）" if s.speculative else ""),
        f"　= √(発見 {s.discovery} × 収益 {s.business})",
        f"　発見スコア（入る余地）: 成長 {s.momentum:.0%} × 競合の空き {s.whitespace:.0%}",
        f"　収益スコア（金になるか）: 需要 {s.evidence.ratio('demand'):.0%}"
        f" × 収益化 {s.monetization:.0%} × 制作相性 {s.production_fit:.0%}"
        f"{'' if s.route_available else '（⚠️ 換金経路なし）'}",
        f"**素点**: {s.total}/100（LLM推測のみだと {s.llm_total}）　"
        f"**実測で埋まった軸**: {s.observed_ratio:.0%}",
        f"**観測回数**: {opportunity.times_seen}回",
        "",
        f"**今やるべきアクション**: {opportunity.action or '未検討'}",
    ]

    if not s.scored:
        lines += ["", "> ⚠️ **未採点** — `ANTHROPIC_API_KEY` が未設定か生成に失敗したため、"
                      "スコアは 0 のままです。数値を判断に使わないでください。"]
    if s.conflicts:
        lines += ["", "> ⚠️ **LLMと実測の食い違い**", *[f"> - {x}" for x in s.conflicts]]
    observed = [f"{a}: 実測 {e.observed}/{e.max_points} "
                f"(source={e.source}, confidence={e.confidence}) {e.note}"
                for a, e in s.evidence.items.items() if e.is_observed]
    if observed or s.notes:
        lines += ["", "<details><summary>実測の内訳とスコアの根拠</summary>", "",
                  "**実測で置き換えた軸**", _bullets(observed, "なし（すべてLLMの推測）"), ""]
        if s.notes:
            lines += ["**メモ**", _bullets(s.notes), ""]
        lines += [f"判定理由: {s.rationale or '（なし）'}", "", "</details>"]
    if r.sources:
        lines += ["", "<details><summary>根拠（参照URL）</summary>", "",
                  _bullets(r.sources[:15]), "", "</details>"]

    lines += ["", f"採用してコンテンツ制作を始める: `/adopt {opportunity.id}` ／ "
                  f"捨てる: `/drop {opportunity.id}`", "", "---", ""]
    return "\n".join(lines)


def render_daily_report(ranked: list[Opportunity], top_n: int = 3,
                        scanned: int = 0) -> str:
    """日次レポート本文。上位 top_n 件だけを詳細表示する。"""
    if not ranked:
        return ("今日は提示できる候補がありませんでした。\n\n"
                "発掘元が有効か（`XAI_API_KEY` / `X_BEARER_TOKEN`）、"
                "`config.yaml` の `scout.discovery_queries` を確認してください。")

    top = ranked[:top_n]
    header = [
        f"{scanned or len(ranked)}件を評価し、上位{len(top)}件を提示します。",
        "",
        "順位は **機会スコア = √(発見スコア × 収益スコア)** で決めています。"
        "相乗平均なので「入る余地はあるが金にならない」「金になるが大手だらけ」の"
        "どちらも上位に来ません。",
        "",
        "**確信度はスコアに掛けていません。** 本当に早いトレンドほど根拠が薄いので、"
        "掛けると成熟したネタばかり上位に来てしまいます。"
        "🎲 が付いた候補は「スコアは高いが根拠が薄い」= 意図的に試す価値がある枠です。",
        "",
        "```",
        "/adopt <id>   採用 → 翌朝からこのテーマでコンテンツが生成される",
        "/drop  <id>   捨てる → 今後この候補は再提示されない",
        "```",
        "",
        "---",
        "",
    ]

    body = [render_opportunity(o, i) for i, o in enumerate(top, start=1)]

    rest = ranked[top_n:]
    if rest:
        rows = ["<details><summary>その他の候補（{}件）</summary>".format(len(rest)), "",
                "| id | ネタ | 機会 | 確信度 | 発見 | 収益 | 判定 |",
                "|---|---|---|---|---|---|---|"]
        for o in rest[:20]:
            rows.append(f"| `{o.id}` | {o.candidate.title[:40]} | {o.score.opportunity} "
                        f"| {o.score.confidence:.2f} | {o.score.discovery} "
                        f"| {o.score.business} | {o.verdict} |")
        rows += ["", "</details>", ""]
        body.extend(rows)

    return "\n".join(header + body)
