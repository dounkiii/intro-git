"""Markdown を素の HTML に変換する。

**なぜ `note_body.py` と別なのか。** あちらは note の非公式APIに合わせて
「段落ごとに UUID を持つ `<p>`」しか出さない、という制約付きの変換器で、
実測できたタグしか使わないようにしてある。こちらは自分のサイトなので普通の
HTML（`<ul>` / `<blockquote>` / `<h2>`）が使える。制約が違うものを1つの
関数にまとめると、片方の都合がもう片方を壊す。

記事は LLM が書くので、生の `<` や `&` を必ずエスケープする。
"""
from __future__ import annotations

import re
from xml.sax.saxutils import escape, quoteattr

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_FENCE = re.compile(r"^\s*```")
_RULE = re.compile(r"^\s*([-*_])\s*(?:\1\s*){2,}$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BARE_URL = re.compile(r"(?<![\"'>=])(https?://[^\s<>()]+)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def inline(text: str) -> str:
    """行内の記法を変換する。エスケープを先に済ませてからタグを差し込む。"""
    out = escape(text)
    out = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _LINK.sub(
        lambda m: f'<a href={quoteattr(m.group(2))} rel="nofollow sponsored" '
                  f'target="_blank">{m.group(1)}</a>', out)
    # 記事末尾の CTA は「ラベル: URL」の形なので、素の URL もリンクにする
    out = _BARE_URL.sub(
        lambda m: f'<a href={quoteattr(m.group(1))} rel="nofollow sponsored" '
                  f'target="_blank">{m.group(1)}</a>', out)
    return out


def to_html(markdown: str) -> str:
    """Markdown を HTML の断片に変換する。

    アフィリエイトリンクには `rel="nofollow sponsored"` を付ける。付けないのは
    検索エンジンのガイドライン違反で、サイト全体の評価を落としうる。
    """
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            items = "".join(f"<li>{inline(b)}</li>" for b in bullets)
            out.append(f"<ul>{items}</ul>")
            bullets.clear()

    def flush() -> None:
        flush_paragraph()
        flush_bullets()

    for raw in lines:
        line = raw.rstrip()

        if _FENCE.match(line):
            if in_code:
                body = "\n".join(escape(c) for c in code)
                out.append(f"<pre><code>{body}</code></pre>")
                code.clear()
            else:
                flush()
            in_code = not in_code
            continue
        if in_code:
            code.append(raw)
            continue

        if not line.strip():
            flush()
            continue

        if _RULE.match(line):
            flush()
            out.append("<hr>")
            continue

        m = _HEADING.match(line)
        if m:
            flush()
            level = min(max(len(m.group(1)), 2), 4)   # h1 はページ側のタイトル
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            continue

        m = _BULLET.match(line) or _ORDERED.match(line)
        if m:
            flush_paragraph()
            bullets.append(m.group(1))
            continue

        m = _QUOTE.match(line)
        if m:
            flush()
            out.append(f"<blockquote>{inline(m.group(1))}</blockquote>")
            continue

        flush_bullets()
        paragraph.append(line.strip())

    if in_code and code:
        out.append("<pre><code>"
                   + "\n".join(escape(c) for c in code) + "</code></pre>")
    flush()
    return "\n".join(out)
