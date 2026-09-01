"""静的サイト書き出しのテスト。

一番守りたいのは**承認ゲート**。公開先が note から Pages に変わっても、
「人が /approve を押したものだけが世に出る」は変えない。お金・税金ジャンルの
法務リスクを最後に1段だけ人間が持つための設計（CLAUDE.md）。
"""
from pathlib import Path

import pytest

from src.config import Config
from src.models import Article, VideoScript
from src.publishers.review_queue import ReviewQueue
from src.publishers.site import PUBLISHABLE, SiteBuilder


def _script(title="タイトル") -> VideoScript:
    return VideoScript(topic_category="tax", title=title,
                       slides=["a"], narration=["あ"])


@pytest.fixture
def queue(tmp_path):
    return ReviewQueue(tmp_path / "review")


def _add(queue, item_id, status, body="本文です。", flags=None, category="tax"):
    article = Article(topic_category=category, title=f"{item_id}の記事",
                      body_markdown=body, monetization_route="なし")
    queue.enqueue(item_id, _script(), Path("dummy.mp4"),
                  safety_flags=flags or [], category=category, article=article)
    if status != "pending":
        queue.set_status(item_id, status)


def test_承認していない記事はサイトに出ない(queue, tmp_path):
    """これが本題。pending が漏れると、人の確認を通っていない税金の記事が
    公開される。"""
    _add(queue, "pending01", "pending")
    _add(queue, "approved01", "approved")

    result = SiteBuilder(Config.load(), queue).build(tmp_path / "site")

    files = " ".join(result["files"])
    assert "approved01" in files
    assert "pending01" not in files
    assert result["articles"] == 1


def test_却下した記事はサイトに出ない(queue, tmp_path):
    _add(queue, "rejected01", "rejected")

    result = SiteBuilder(Config.load(), queue).build(tmp_path / "site")

    assert result["articles"] == 0


def test_公開してよい状態にpendingが入っていない():
    """定数を書き換えて承認ゲートを緩めるのを防ぐ。"""
    assert "pending" not in PUBLISHABLE
    assert "rejected" not in PUBLISHABLE
    assert set(PUBLISHABLE) <= {"approved", "published"}


def test_本文が空の記事は出さない(queue, tmp_path):
    """台本だけあって記事が無い項目が index に空リンクとして並ぶのを防ぐ。"""
    _add(queue, "empty01", "approved", body="")

    result = SiteBuilder(Config.load(), queue).build(tmp_path / "site")

    assert result["articles"] == 0


def test_記事のHTMLはエスケープされる(queue, tmp_path):
    """記事は LLM が書く。生のタグを通すと自分のサイトに XSS を置くことになる。"""
    payload = "<" + "script>alert(1)</" + "script>"
    _add(queue, "esc01", "approved", body=f"5 < 10 & 3 > 1 {payload}")

    SiteBuilder(Config.load(), queue).build(tmp_path / "site")
    text = (tmp_path / "site/articles/esc01.html").read_text(encoding="utf-8")

    assert payload not in text
    assert "&lt;script&gt;" in text
    assert "5 &lt; 10 &amp; 3 &gt; 1" in text


def test_アフィリエイトリンクにnofollowが付く(queue, tmp_path):
    """付けないと検索エンジンのガイドライン違反で、サイト全体の評価を落とす。"""
    _add(queue, "aff01", "approved",
         body="申し込みは [ここ](https://example.com/aff?id=1) から。")

    SiteBuilder(Config.load(), queue).build(tmp_path / "site")
    text = (tmp_path / "site/articles/aff01.html").read_text(encoding="utf-8")

    assert 'rel="nofollow sponsored"' in text


def test_広告表示は本文より前に出る(queue, tmp_path, monkeypatch):
    """景表法のステマ規制。末尾に置くと読まれない位置に埋もれる。"""
    monkeypatch.setenv("AFF_ACCOUNTING_SOFT", "https://example.com/soft")
    _add(queue, "ad01", "approved", body="本文の始まり。")

    SiteBuilder(Config.load(), queue).build(tmp_path / "site")
    text = (tmp_path / "site/articles/ad01.html").read_text(encoding="utf-8")

    assert 'class="disclosure"' in text
    assert text.index("disclosure") < text.index("本文の始まり")


def test_免責がすべてのページに出る(queue, tmp_path):
    """税理士法。個別の税務判断を請け負う形にしない。"""
    _add(queue, "d01", "approved")

    SiteBuilder(Config.load(), queue).build(tmp_path / "site")

    for name in ("index.html", "articles/d01.html"):
        text = (tmp_path / "site" / name).read_text(encoding="utf-8")
        assert "税理士" in text, name


def test_承認が0件でもサイトは壊れない(queue, tmp_path):
    """/approve を押していない日に index が落ちると、公開済みの記事も消える。"""
    result = SiteBuilder(Config.load(), queue).build(tmp_path / "site")

    index = (tmp_path / "site/index.html").read_text(encoding="utf-8")

    assert result["articles"] == 0
    assert "<h1>" in index


def test_Jekyllを無効にするファイルを置く(queue, tmp_path):
    """置かないと _ で始まるファイルが Pages 側で無視される。"""
    SiteBuilder(Config.load(), queue).build(tmp_path / "site")

    assert (tmp_path / "site/.nojekyll").exists()


def test_スマホで読める幅指定がある(queue, tmp_path):
    """オーナーの読者は通勤中のスマホを想定している。"""
    _add(queue, "m01", "approved")

    SiteBuilder(Config.load(), queue).build(tmp_path / "site")
    text = (tmp_path / "site/articles/m01.html").read_text(encoding="utf-8")

    assert "width=device-width" in text


def test_公開ワークフローが承認済みだけを出す():
    """ワークフローが別のコマンドを呼んでいたら、ゲートを通らない経路ができる。"""
    text = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")

    assert "src.pipeline site" in text
    # 承認前の生成コマンドを Pages のワークフローから呼んでいないこと
    assert "pipeline run" not in text
    assert "publish --approved" not in text


def test_配信ワークフローは承認済みだけを出す():
    """手動起動できる配信経路を足したので、そこから pending が漏れないことを
    確かめる。承認するのは人、配信を再実行するのは機械、という切り分け。"""
    raw = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")
    # コメント行は除く。説明文に書いた `/approve` を「実行している」と
    # 誤判定しないため（test_layer_contract の _code_of と同じ理由）。
    text = "\n".join(l for l in raw.splitlines()
                     if not l.lstrip().startswith("#"))

    assert "publish --approved" in text
    assert "REVIEW_REQUIRED: 'true'" in text, \
        "REVIEW_REQUIRED が false だと pending も配信される"
    # 承認そのものを機械が押す経路になっていないこと
    assert "/approve" not in text
    assert "pipeline command" not in text


def test_承認のあとにサイトが更新される():
    """GitHub は GITHUB_TOKEN による push でワークフローを起動しない（再帰実行を
    防ぐ仕様）。承認コマンドは bot として push するので、paths に
    data/review_queue/** を入れていても pages は動かない。

    2026-08-31 の /approve all で実際に起きた: note には4本出たのに
    **サイトは2本のまま**だった。承認したのに公開されない形は、
    人が押した操作が黙って消えるのと同じ。
    """
    import yaml

    doc = yaml.safe_load(
        Path(".github/workflows/pages.yml").read_text(encoding="utf-8"))
    # yaml は `on` を True と解釈する
    triggers = doc.get("on") or doc.get(True)

    assert "workflow_run" in triggers, \
        "承認のあとにサイトを更新する経路がない"
    watched = triggers["workflow_run"]["workflows"]
    assert "approve-command" in watched
    assert "publish" in watched
