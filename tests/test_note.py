"""note 投稿のテスト。

守りたいのは4つ。

1. **実測できた形を崩さない。** draft_save の payload はオーナーのブラウザで
   実際に確認できた唯一のリクエスト
2. **認証情報を漏らさない。** このリポジトリは public で Actions のログも見える
3. **既定は下書き。** 非公式APIで、こちらでは実行して確かめられていない
4. **同じ記事の下書きを毎晩作り直さない。** 承認済み1本につき下書きが
   毎日1件増えるのを防ぐ
"""
import logging

import pytest
import requests

from src.config import Config
from src.models import Article
from src.publishers.note import (API, COOKIE_NAME, SESSION_ENV, XSRF_ENV,
                                 NoteIdStore, NotePublisher)


def _article(**kw) -> Article:
    base = dict(topic_category="tax", title="ふるさと納税の上限",
                body_markdown="テストです。", monetization_route="なし")
    base.update(kw)
    return Article(**base)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv(SESSION_ENV, "SECRET_SESSION_VALUE")
    monkeypatch.delenv(XSRF_ENV, raising=False)


@pytest.fixture
def store(tmp_path):
    return NoteIdStore(tmp_path / "note_ids.json")


class Recorder:
    """requests.request を差し替えて、送ったものを覚える。"""

    def __init__(self, responses=None):
        self.calls: list[dict] = []
        self.responses = responses or {}

    def __call__(self, method, url, json=None, headers=None, cookies=None,
                 timeout=None):
        self.calls.append(dict(method=method, url=url, json=json,
                               headers=headers, cookies=cookies))
        body = self.responses.get(url.split("?")[0], {"data": {}})
        if callable(body):
            body = body(url)
        return _Resp(body)

    def call(self, needle: str) -> dict:
        for c in self.calls:
            if needle in c["url"]:
                return c
        raise AssertionError(f"{needle} のリクエストがありません: "
                             f"{[c['url'] for c in self.calls]}")


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.fixture
def net(monkeypatch):
    rec = Recorder({API: {"data": {"id": 177206277, "key": "nabc123",
                                   "slug": "nabc123"}}})
    monkeypatch.setattr(requests, "request", rec)
    return rec


# --- Secret ----------------------------------------------------------------

def test_Secretが欠けていたら投稿しない(monkeypatch, store):
    monkeypatch.delenv(SESSION_ENV, raising=False)

    result = NotePublisher(store=store).publish(_article())

    assert result["skipped"] == "secrets_missing"
    assert result["missing"] == [SESSION_ENV]


def test_XSRFは無くても投稿できる(creds, net, store):
    """公開実装3件のうち1件は X-XSRF-TOKEN を送っていない。必須にすると、
    取れない環境で投稿が止まる。"""
    result = NotePublisher(store=store).publish(_article())

    assert "skipped" not in result
    assert "X-XSRF-TOKEN" not in net.calls[0]["headers"]


def test_XSRFがあれば送る(creds, net, store, monkeypatch):
    monkeypatch.setenv(XSRF_ENV, "SECRET_XSRF")

    NotePublisher(store=store).publish(_article())

    assert net.calls[0]["headers"]["X-XSRF-TOKEN"] == "SECRET_XSRF"


# --- リクエストの形 --------------------------------------------------------

def test_新規作成のリクエスト(creds, net, store):
    """?id= に入れる ID をもらうために最初に呼ぶ。"""
    NotePublisher(store=store).publish(_article())
    call = net.call("text_notes")

    assert net.calls[0]["method"] == "POST"
    assert net.calls[0]["url"] == API
    assert net.calls[0]["json"] == {"template_key": None}
    assert call["cookies"] == {COOKIE_NAME: "SECRET_SESSION_VALUE"}


def test_下書き保存のpayloadが実測どおり(creds, net, store):
    """基準はオーナーのブラウザで実際に下書き保存したときのリクエスト。
    body / body_length / index / is_lead_form / name の5つ。"""
    NotePublisher(store=store).publish(_article())
    call = net.call("draft_save")

    assert call["method"] == "POST"
    assert "id=177206277" in call["url"] and "is_temp_saved=true" in call["url"]
    assert set(call["json"]) == {"body", "body_length", "index",
                                 "is_lead_form", "name"}
    assert call["json"]["name"] == "ふるさと納税の上限"
    assert call["json"]["index"] is False
    assert call["json"]["is_lead_form"] is False


def test_body_lengthは本文の文字数(creds, net, store):
    """実測では「テストです。」6文字に対して 6 だった。公開実装2件は
    len(body_html) を送っていたが、**推測より実測を採る。**"""
    NotePublisher(store=store).publish(_article(body_markdown="テストです。"))
    call = net.call("draft_save")

    assert call["json"]["body_length"] == 6
    assert len(call["json"]["body"]) > 6      # HTML の長さではない


def test_本文はnoteのHTMLで送る(creds, net, store):
    """note の下書き保存APIは Markdown を受け取らない。"""
    NotePublisher(store=store).publish(_article())
    body = net.call("draft_save")["json"]["body"]

    assert body.startswith("<p name=")
    assert "テストです。" in body


# --- 下書きと公開 ----------------------------------------------------------

def test_既定は下書きで公開まで行かない(creds, net, store):
    """非公式APIで、こちらでは実行して確かめられていない。1本目は
    オーナーが note の画面で書式を確認する。"""
    result = NotePublisher(store=store).publish(_article())

    assert result["draft"] is True
    assert not any(c["method"] == "PUT" for c in net.calls)
    assert "editor.note.com" in result["url"]


def test_設定で公開に切り替えられる(creds, net, store):
    config = Config.load()
    config.section("publishing")["note_draft"] = False

    result = NotePublisher(config, store=store).publish(_article())
    call = net.call(f"{API}/177206277")

    assert result["draft"] is False
    assert call["method"] == "PUT"
    assert call["json"]["status"] == "published"
    assert call["json"]["price"] == 0
    assert call["json"]["free_body"].startswith("<p name=")


def test_公開時のハッシュタグは名前だけの形にする(creds, net, store):
    config = Config.load()
    config.section("publishing")["note_draft"] = False
    config.section("publishing")["hashtags"] = ["#税金", "ふるさと納税"]

    NotePublisher(config, store=store).publish(_article())
    tags = net.call(f"{API}/177206277")["json"]["hashtags"]

    assert tags == [{"name": "税金"}, {"name": "ふるさと納税"}]


# --- 下書きを作り直さない --------------------------------------------------

def test_同じ記事の下書きを作り直さない(creds, net, store):
    """毎晩の実行で作り直すと、承認済み1本につき下書きが毎日1件増える。"""
    NotePublisher(store=store).publish(_article(), item_id="tax-t1")
    first = len([c for c in net.calls if c["url"] == API])

    NotePublisher(store=store).publish(_article(), item_id="tax-t1")
    second = len([c for c in net.calls if c["url"] == API])

    assert first == 1
    assert second == 1, "2回目も新規作成している"
    # 下書き保存は2回とも走る（本文の更新のため）
    assert len([c for c in net.calls if "draft_save" in c["url"]]) == 2


def test_作成できた時点でIDを覚える(creds, net, store):
    """下書き保存が落ちても ID を残す。残さないと次回また作られる。"""
    NotePublisher(store=store).publish(_article(), item_id="tax-t1")

    assert store.get("tax-t1")["id"] == "177206277"


def test_台帳が壊れていても投稿は止まらない(creds, net, store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("これはJSONではない", encoding="utf-8")

    result = NotePublisher(store=store).publish(_article(), item_id="x")

    assert "skipped" not in result and "error" not in result


# --- 失敗の扱い ------------------------------------------------------------

def test_通信が失敗しても例外を投げない(creds, store, monkeypatch):
    """毎朝の cron を1回の障害で止めない。"""
    def boom(*a, **k):
        raise requests.ConnectionError("接続できません")

    monkeypatch.setattr(requests, "request", boom)

    result = NotePublisher(store=store).publish(_article())

    assert "error" in result


def test_認証エラーは取り直すSecret名を出す(creds, store, monkeypatch, caplog):
    """note の Cookie はログインし直すと変わる。何を差し替えればいいか
    分からないと直せない。"""
    class Resp:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError("401", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        NotePublisher(store=store).publish(_article())

    assert SESSION_ENV in caplog.text


def test_IDが返らなければ下書き保存に進まない(creds, store, monkeypatch):
    """note 側の仕様が変わって id が来なくなったとき、?id= が空のまま
    リクエストを送ると何が起きるか分からない。"""
    rec = Recorder({API: {"data": {}}})
    monkeypatch.setattr(requests, "request", rec)

    result = NotePublisher(store=store).publish(_article())

    assert result["error"] == "no_id"
    assert not any("draft_save" in c["url"] for c in rec.calls)


def test_認証情報をログに出さない(creds, store, monkeypatch, caplog):
    """このリポジトリは public。Actions のログも public に見える。"""
    class Resp:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level(logging.DEBUG):
        result = NotePublisher(store=store).publish(_article())

    blob = caplog.text + repr(result)
    assert "SECRET_SESSION_VALUE" not in blob


# --- ワークフローとの結線 ---------------------------------------------------

def test_投稿するワークフローにSecretが渡っている():
    """#6 の再発防止。Secrets を登録しても env に書き忘れると、ランナーでは
    常に空になり「登録したのに動かない」になる。"""
    import pathlib

    text = pathlib.Path(".github/workflows/approve-command.yml").read_text(
        encoding="utf-8")
    publish_step = text[text.index("publish --approved") - 2000:]

    for name in (SESSION_ENV, XSRF_ENV):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in text, name
        assert name in publish_step, f"{name} が publish ステップに渡っていない"


def test_承認したらnoteにも出る():
    """承認から投稿までを人が繋がない。手でコピペしないための結線。"""
    import inspect

    from src.pipeline import Pipeline

    src = inspect.getsource(Pipeline.publish_approved)

    assert "self.note.publish" in src
    # 下書きを作り直さないよう item_id を渡していること
    assert "item_id=item.id" in src


def test_公開先は独立に動く():
    """片方の Secret が無いときにもう片方も出なくなると、
    「note の準備ができるまで何も公開されない」に戻る。"""
    import inspect

    from src.pipeline import Pipeline

    src = inspect.getsource(Pipeline.publish_approved)
    note_at = src.index("self.note.publish")
    hatena_at = src.index("self.hatena.publish")

    # 片方の結果で他方を分岐させていない（同じ深さで並んでいる）
    between = src[note_at:hatena_at]
    assert "if " not in between, "note の結果で hatena の実行を分けています"
