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
        f"**収益性スコア**: {s.monetizability}/20　"
        f"**総合スコア**: {s.total}/100"
        f"（LLM {s.llm_total} {s.machine_adjust:+d} 補正）",
        f"**早期シグナル**（成長性×競合の少なさ）: {s.early_signal}",
        f"**観測回数**: {opportunity.times_seen}回",
        "",
        f"**今やるべきアクション**: {opportunity.action or '未検討'}",
    ]

    if not s.scored:
        lines += ["", "> ⚠️ **未採点** — `ANTHROPIC_API_KEY` が未設定か生成に失敗したため、"
                      "スコアは 0 のままです。数値を判断に使わないでください。"]
    if s.conflicts:
        lines += ["", "> ⚠️ **LLMと実測の食い違い**", *[f"> - {x}" for x in s.conflicts]]
    if s.adjust_reasons:
        lines += ["", f"<details><summary>スコア補正の内訳</summary>\n\n"
                      f"{_bullets(s.adjust_reasons)}\n\n"
                      f"判定理由: {s.rationale or '（なし）'}\n\n</details>"]
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
        "順位は合計点ではなく**早期シグナル（成長性×競合の少なさ）**で決めています。"
        "すでに大流行しているテーマを上位に出さないためです。",
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
                "| id | ネタ | 総合 | 早期シグナル | 判定 |",
                "|---|---|---|---|---|"]
        for o in rest[:20]:
            rows.append(f"| `{o.id}` | {o.candidate.title[:40]} | {o.score.total} "
                        f"| {o.score.early_signal} | {o.verdict} |")
        rows += ["", "</details>", ""]
        body.extend(rows)

    return "\n".join(header + body)
