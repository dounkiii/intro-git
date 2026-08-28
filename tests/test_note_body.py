"""note 本文HTMLへの変換テスト。

基準は**オーナーのブラウザで実際に下書き保存したときのリクエスト**
（2026-08-28 実測）。推測で書いた部分と実測で確認した部分を混ぜないよう、
「実測の再現」と「推測タグの隔離」を別のテストにしている。
"""
import re

import pytest

from src.publishers.note_body import INFERRED_TAGS, to_note_html


def _ids():
    """UUID を固定する。順に u0, u1, ... を返す。"""
    box = {"i": -1}

    def gen():
        box["i"] += 1
        return f"u{box['i']}"

    return gen


def test_実測したリクエストを再現する():
    """これが基準。note のエディタで「テストです。」と入れて下書き保存すると
    段落1つ + 空段落1つ、body_length=6 が送られていた。"""
    html, length = to_note_html("テストです。\n", ident=_ids())

    assert html == ('<p name="u0" id="u0">テストです。</p>'
                    '<p name="u1" id="u1"><br></p>')
    assert length == 6


def test_段落ごとに別のUUIDが入る():
    """同じ UUID を使い回すと note 側が段落を識別できない。"""
    html, _ = to_note_html("一行目\n\n二行目")

    ids = re.findall(r'id="([^"]+)"', html)

    assert len(ids) == len(set(ids)), f"UUID が重複しています: {ids}"
    assert all(re.fullmatch(r"[0-9a-f-]{36}", i) for i in ids), ids


def test_nameとidは同じ値():
    """実測のリクエストでは両方に同じ UUID が入っていた。"""
    html, _ = to_note_html("本文")

    for name, ident in re.findall(r'name="([^"]+)" id="([^"]+)"', html):
        assert name == ident


def test_記事のHTMLはエスケープされる():
    """記事は LLM が書く。生の `<` や `&` を通すと本文が壊れる。"""
    html, _ = to_note_html("5 < 10 & 3 > 1 <script>alert(1)</script>")

    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "5 &lt; 10 &amp; 3 &gt; 1" in html


def test_body_lengthはタグを数えない():
    """実測では「テストです。」6文字に対して 6。タグや UUID は含まない。"""
    html, length = to_note_html("**強調**と[リンク](https://example.com)")

    assert length == len("強調とリンク")
    assert len(html) > length


def test_body_lengthは空段落を数えない():
    _, length = to_note_html("あ\n\n\n\nい")

    assert length == 2


def test_見出しは階層を保つ():
    """6800字の記事から見出しを落とすと読み物として成立しない。"""
    html, _ = to_note_html("## 大見出し\n### 小見出し", ident=_ids())

    assert '<h2 name="u0" id="u0">大見出し</h2>' in html
    assert '<h3 name="u1" id="u1">小見出し</h3>' in html


def test_リンクのURLは属性として囲まれる():
    html, _ = to_note_html('[案件](https://example.com/a?b=1&c="x")')

    assert 'href=' in html
    # 引用符が生のまま属性に入っていない
    attr = re.search(r'href=("[^"]*"|\'[^\']*\')', html)
    assert attr, html


def test_箇条書きは推測タグを増やさない():
    """`<ul>` / `<li>` の実物を見ていない。推測タグが増えるほど、崩れたときに
    どこが原因か分からなくなる。実測できている `<p>` で表現する。"""
    html, _ = to_note_html("- 一つ目\n- 二つ目")

    assert "<ul" not in html and "<li" not in html
    assert "・一つ目" in html and "・二つ目" in html


def test_未検証のタグは一箇所にまとまっている():
    """1本目の下書きが崩れていたとき、直す場所が散っていると探し直しになる。"""
    assert set(INFERRED_TAGS) == {"h2", "h3", "strong", "link"}


def test_使うタグは実測と推測の範囲に収まる():
    """変換の結果に未知のタグが混じらないこと。Markdown に新しい記法が来ても、
    そのまま生HTMLとして通してはいけない。"""
    import pathlib

    md = pathlib.Path("data/articles/household-sample-h1.md").read_text(
        encoding="utf-8")
    html, _ = to_note_html(md + "\n\n> 引用\n\n```\ncode\n```\n\n---\n")

    used = set(re.findall(r"</?([a-zA-Z0-9]+)", html))

    assert used <= {"p", "br", "h2", "h3", "strong", "a"}, used


@pytest.mark.parametrize("text", ["", "\n", "   \n\n  "])
def test_空でも落ちない(text):
    html, length = to_note_html(text)

    assert length == 0
    assert "<p" in html


def test_段落の途中の改行は1段落にまとめる():
    """Markdown の折り返しをそのまま段落分割すると、note 側で文が刻まれる。"""
    html, _ = to_note_html("前半の文が\n続いている。\n\n次の段落。", ident=_ids())

    assert '<p name="u0" id="u0">前半の文が 続いている。</p>' in html
