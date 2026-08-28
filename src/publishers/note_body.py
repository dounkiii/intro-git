"""記事本文（Markdown）を note の本文HTMLに変換する。

**なぜ変換が必要か。** note の下書き保存APIは Markdown を受け取らない。
オーナーのブラウザで実際に下書き保存したときのリクエストを見ると、本文は
**段落ごとに UUID を持つHTML**だった（`draft_save` の payload、2026-08-28 実測）。

    body: '<p name="a056a569-...">テストです。</p>'
          '<p name="1643cc8f-..."><br></p>'
    body_length: 6      # 「テストです。」の文字数。空段落は 0

`name` と `id` には同じ UUID が入る。note のエディタが段落を識別するための
ものなので、こちら側で生成した UUID をそのまま入れる。

**どこまでが実測で、どこからが推測か。** ここを混ぜると後で直せなくなるので
分けて書く。

  実測（上のキャプチャで確認）
    - 段落は `<p name="{uuid}" id="{uuid}">本文</p>`
    - 空行は `<br>` だけを持つ段落
    - `body_length` は本文の文字数（タグを除く）

  推測（未検証。`INFERRED_TAGS` にまとめてある）
    - 見出しが `<h2>` / `<h3>`
    - 強調が `<strong>`、リンクが `<a href>`

推測部分があるので、**初回は必ず下書き**にする（`publishing.note_draft`）。
オーナーが1本目を note の画面で見れば、崩れていればその場で分かる。
崩れていた要素だけ `INFERRED_TAGS` を直せばよく、変換全体を疑わなくて済む。

箇条書きと引用は**推測を増やさないために段落に落とす**（`・` を付けた `<p>`）。
実測できている要素だけで表現できるので、崩れる余地がない。見出しと違って
見た目の劣化も小さい。
"""
from __future__ import annotations

import re
import uuid as _uuid
from typing import Callable
from xml.sax.saxutils import escape, quoteattr

# 未検証のタグ。キャプチャが取れたらここだけ直す。
INFERRED_TAGS = {"h2": "h2", "h3": "h3", "strong": "strong", "link": "a"}

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_FENCE = re.compile(r"^\s*```")
_RULE = re.compile(r"^\s*([-*_])\s*(?:\1\s*){2,}$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _inline(text: str) -> str:
    """行内の強調とリンクだけを変換する。

    エスケープを先に済ませてからタグを差し込む。記事は LLM が書くので
    `<` や `&` がそのまま入りうる。
    """
    out = escape(text)
    strong = INFERRED_TAGS["strong"]
    link = INFERRED_TAGS["link"]

    # エスケープ後なので Markdown 記法の文字（* [ ] ( )）は変わっていない
    out = _BOLD.sub(lambda m: f"<{strong}>{m.group(1)}</{strong}>", out)

    def _a(m: re.Match) -> str:
        label, href = m.group(1), m.group(2)
        # href は escape 済みの文字列。属性として安全に囲む
        return f'<{link} href={quoteattr(href)}>{label}</{link}>'

    return _LINK.sub(_a, out)


def _visible(text: str) -> str:
    """`body_length` 用に、タグを除いた本文を返す。"""
    return re.sub(r"<[^>]+>", "", text)


def _block(tag: str, inner: str, ident: str) -> str:
    attrs = f'name="{ident}" id="{ident}"'
    return f"<{tag} {attrs}>{inner}</{tag}>"


def to_note_html(markdown: str,
                 ident: Callable[[], str] | None = None) -> tuple[str, int]:
    """Markdown を note の本文HTMLに変換し、(html, body_length) を返す。

    `ident` はテストで UUID を固定するための差し替え口。既定は uuid4。
    """
    new_id = ident or (lambda: str(_uuid.uuid4()))
    blocks: list[str] = []
    visible = 0

    def emit(tag: str, inner: str) -> None:
        nonlocal visible
        blocks.append(_block(tag, inner, new_id()))
        visible += len(_visible(inner))

    def blank() -> None:
        blocks.append(_block("p", "<br>", new_id()))

    lines = markdown.replace("\r\n", "\n").split("\n")
    paragraph: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            emit("p", _inline(" ".join(paragraph)))
            paragraph.clear()

    for raw in lines:
        line = raw.rstrip()

        if _FENCE.match(line):
            if in_code:
                # コードブロックは推測タグを増やさないよう段落に落とす
                emit("p", "<br>".join(escape(c) for c in code))
                code.clear()
            else:
                flush_paragraph()
            in_code = not in_code
            continue
        if in_code:
            code.append(raw)
            continue

        if not line.strip():
            flush_paragraph()
            blank()
            continue

        if _RULE.match(line):
            flush_paragraph()
            blank()
            continue

        m = _HEADING.match(line)
        if m:
            flush_paragraph()
            level = len(m.group(1))
            # note の見出しは2段階。#（記事タイトル相当）も h2 に寄せる
            tag = INFERRED_TAGS["h2"] if level <= 2 else INFERRED_TAGS["h3"]
            emit(tag, _inline(m.group(2)))
            continue

        m = _BULLET.match(line)
        if m:
            flush_paragraph()
            emit("p", "・" + _inline(m.group(1)))
            continue

        m = _ORDERED.match(line)
        if m:
            flush_paragraph()
            emit("p", f"{m.group(1)}. " + _inline(m.group(2)))
            continue

        m = _QUOTE.match(line)
        if m:
            flush_paragraph()
            emit("p", "「" + _inline(m.group(1)) + "」")
            continue

        paragraph.append(line.strip())

    if in_code and code:
        emit("p", "<br>".join(escape(c) for c in code))
    flush_paragraph()

    return "".join(blocks), visible
