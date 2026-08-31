"""承認済みの記事を静的サイトとして書き出す。

**なぜこれを作ったのか。** note には公式APIが無く、キャプチャにはオーナーの
PC作業が必要で、それが止まっていた。はてなは公式APIだがアカウント作成と
Secret 登録が要る。**どの公開先も、オーナーの作業なしには使えない。**

GitHub Pages はこのリポジトリの中で完結するので、必要なのは Pages を有効に
する1回の操作だけで、以後は push するだけで公開される。認証情報も要らない。
「収益0円のまま公開0件」を抜けるための、一番手数の少ない道として用意した。

**承認ゲートは維持する。** サイトに出るのは人間が `/approve` を押したものだけ。
`pending` は絶対に出さない。お金・税金ジャンルの法務リスクを人間が最後に
1段持つ設計（`CLAUDE.md`）は、公開先が変わっても変えない。

note を捨てたわけではない。`src/publishers/note.py` はキャプチャが揃えば動く。
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..monetize.affiliate import AffiliateEngine
from .markdown import to_html
from .review_queue import ReviewItem, ReviewQueue

logger = logging.getLogger(__name__)

# サイトに出してよい状態。**pending は入れない。**
PUBLISHABLE = ("approved", "published")

_STYLE = """
:root { color-scheme: light dark;
  --bg:#fbfbf9; --fg:#1a1a1a; --muted:#5c5c5c; --line:#e2e0da; --accent:#1f5f8b; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#15161a; --fg:#e8e8e6; --muted:#a0a0a0; --line:#2e3037; --accent:#7db4de; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.85 -apple-system, "Hiragino Kaku Gothic ProN", "Yu Gothic",
  system-ui, sans-serif; }
.wrap { max-width:44rem; margin:0 auto; padding:1.5rem 1.25rem 4rem; }
header a { color:var(--muted); text-decoration:none; font-size:.85rem; }
h1 { font-size:1.6rem; line-height:1.4; margin:1.5rem 0 .5rem; }
h2 { font-size:1.2rem; margin:2.2rem 0 .6rem; padding-top:.4rem;
  border-top:1px solid var(--line); }
h3 { font-size:1.05rem; margin:1.6rem 0 .4rem; }
p, li { overflow-wrap:anywhere; }
a { color:var(--accent); }
ul { padding-left:1.3rem; }
blockquote { margin:1rem 0; padding:.2rem 0 .2rem 1rem;
  border-left:3px solid var(--line); color:var(--muted); }
pre { overflow-x:auto; background:rgba(127,127,127,.12); padding:.8rem;
  border-radius:6px; }
.meta { color:var(--muted); font-size:.85rem; }
.disclosure { background:rgba(127,127,127,.12); border:1px solid var(--line);
  border-radius:6px; padding:.7rem .9rem; font-size:.88rem; margin:1rem 0 1.5rem; }
.index-list { list-style:none; padding:0; }
.index-list li { padding:1.1rem 0; border-bottom:1px solid var(--line); }
.index-list a { font-size:1.05rem; font-weight:600; text-decoration:none; }
footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line);
  color:var(--muted); font-size:.8rem; }
"""


def _page(title: str, body: str, home: str = "index.html") -> str:
    """1ページ分の HTML。テンプレートエンジンを入れないのは依存を増やさないため。"""
    t = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
<header><a href="{home}">← お金の手続きメモ</a></header>
{body}
<footer>
このサイトの記事は自動生成し、公開前に人が確認しています。
制度の内容は変わることがあるため、実際の手続きは必ず公式情報で確認してください。
個別の税務判断は税理士等の専門家にご相談ください。
</footer>
</div>
</body>
</html>
"""


def _slug(item_id: str) -> str:
    """ファイル名にする。ID は自前で作っているので英数と - _ しか来ない。"""
    return "".join(c for c in item_id if c.isalnum() or c in "-_") or "article"


class SiteBuilder:
    def __init__(self, config: Config | None = None,
                 queue: ReviewQueue | None = None):
        self.config = config or Config.load()
        self.queue = queue or ReviewQueue()
        self.affiliate = AffiliateEngine(self.config)

    def publishable(self) -> list[ReviewItem]:
        """サイトに出す記事。承認済みで、本文があるものだけ。"""
        out = []
        for status in PUBLISHABLE:
            for item in self.queue.list_items(status=status):
                if (item.article or {}).get("body_markdown"):
                    out.append(item)
        return out

    def render_article(self, item: ReviewItem) -> str:
        article = item.article or {}
        title = article.get("title") or (item.script or {}).get("title") or item.id
        block = self.affiliate.build(item.category or "general", quiet=True)

        parts = [f"<h1>{html.escape(title)}</h1>"]

        disclosure = self.affiliate.disclosure_header(block)
        if disclosure:
            # 景表法のステマ規制。**本文より前**に出す。末尾に置くと埋もれる。
            parts.append(f'<div class="disclosure">{html.escape(disclosure)}</div>')

        parts.append(to_html(article["body_markdown"]))

        cta = self.affiliate.article_cta_section(block)
        if cta:
            parts.append(to_html(cta))

        sources = article.get("source_urls") or []
        if sources:
            links = "".join(
                f'<li><a href="{html.escape(u)}" rel="nofollow" '
                f'target="_blank">{html.escape(u)}</a></li>' for u in sources)
            parts.append(f"<h2>参考にした投稿</h2><ul>{links}</ul>")

        return _page(title, "\n".join(parts))

    def render_index(self, items: list[ReviewItem]) -> str:
        if not items:
            body = ("<h1>お金の手続きメモ</h1>"
                    "<p>公開できる記事がまだありません。</p>")
            return _page("お金の手続きメモ", body)

        rows = []
        for item in items:
            article = item.article or {}
            title = article.get("title") or item.id
            rows.append(
                f'<li><a href="articles/{_slug(item.id)}.html">'
                f"{html.escape(title)}</a>"
                f'<div class="meta">{html.escape(item.category or "")}</div></li>')
        body = ("<h1>お金の手続きメモ</h1>"
                "<p>税金・補助金・社会保険の「結局どうすればいいか」を短くまとめています。</p>"
                f'<ul class="index-list">{"".join(rows)}</ul>')
        return _page("お金の手続きメモ", body)

    def build(self, out_dir: Path) -> dict:
        """サイトを書き出す。書いたファイルの一覧を返す。"""
        items = self.publishable()
        articles_dir = out_dir / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        for item in items:
            path = articles_dir / f"{_slug(item.id)}.html"
            path.write_text(self.render_article(item), encoding="utf-8")
            written.append(str(path.relative_to(out_dir)))

        (out_dir / "index.html").write_text(
            self.render_index(items), encoding="utf-8")
        written.append("index.html")

        # Jekyll に処理させない（_ で始まるファイルを無視されるのを防ぐ）
        (out_dir / ".nojekyll").write_text("", encoding="utf-8")

        logger.info("サイトを書き出しました: 記事%d件 → %s", len(items), out_dir)
        return {"articles": len(items), "files": written,
                "built_at": datetime.now(timezone.utc).isoformat()}
