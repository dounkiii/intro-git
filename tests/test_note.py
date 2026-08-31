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
from src.publishers.note import (API, EXTRA_ENV, GQL_COOKIE, GQL_ENV,
                                 SESSION_COOKIE, SESSION_ENV, XSRF_ENV,
                                 NoteIdStore, NotePublisher)


def _article(**kw) -> Article:
    base = dict(topic_category="tax", title="ふるさと納税の上限",
                body_markdown="テストです。", monetization_route="なし")
    base.update(kw)
    return Article(**base)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv(SESSION_ENV, "SECRET_SESSION_VALUE")
    monkeypatch.setenv(GQL_ENV, "SECRET_GQL_TOKEN")
    monkeypatch.delenv(XSRF_ENV, raising=False)
    monkeypatch.delenv(EXTRA_ENV, raising=False)


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
    for name in (SESSION_ENV, GQL_ENV):
        monkeypatch.delenv(name, raising=False)

    result = NotePublisher(store=store).publish(_article())

    assert result["skipped"] == "secrets_missing"
    assert set(result["missing"]) == {SESSION_ENV, GQL_ENV}


def test_認証トークンだけ欠けていても止まる(monkeypatch, store):
    """`_note_session_v5` だけでは 403 になる（2026-08-31 実測）。
    手前で止めて、足りない Secret 名を出す。"""
    monkeypatch.setenv(SESSION_ENV, "SECRET_SESSION_VALUE")
    monkeypatch.delenv(GQL_ENV, raising=False)

    result = NotePublisher(store=store).publish(_article())

    assert result["missing"] == [GQL_ENV]


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
    assert call["cookies"] == {SESSION_COOKIE: "SECRET_SESSION_VALUE",
                               GQL_COOKIE: "SECRET_GQL_TOKEN"}


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

def test_コードの既定は下書き(creds, net, store):
    """config に note_draft が無いときは下書きに倒す。

    新しい外部連携が初回から公開すると、書式崩れに気づく前に世に出る。
    **live の config を読まない。** 運用で公開に切り替えた途端にこのテストが
    落ちると、「設定を変えたらテストが赤くなる」ノイズになる。
    """
    config = Config.load()
    config.section("publishing").pop("note_draft", None)

    assert NotePublisher(config, store=store).draft is True


def test_下書きなら公開まで行かない(creds, net, store):
    """下書き設定のときに PUT が飛ばないこと。"""
    config = Config.load()
    config.section("publishing")["note_draft"] = True

    result = NotePublisher(config, store=store).publish(_article())

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


def test_既定ではハッシュタグを送らない(creds, net, store):
    """`[{"name": "税金"}]` は note に拒否された（HTTP 400
    `hashtags is invalid`、2026-08-31 実測）。正しい形が分からないまま
    当てにいくと、そのたびに本番アカウントで試すことになる。
    タグは公開の必須項目ではないので、まず記事を出す方を採る。"""
    config = Config.load()
    config.section("publishing")["note_draft"] = False
    config.section("publishing")["hashtags"] = ["#税金", "ふるさと納税"]

    NotePublisher(config, store=store).publish(_article())

    assert net.call(f"{API}/177206277")["json"]["hashtags"] == []


def test_形が分かったらタグを送れる(creds, net, store):
    """実測できたら config 1行で有効にできること。"""
    config = Config.load()
    config.section("publishing")["note_draft"] = False
    config.section("publishing")["note_hashtags"] = True
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

    for name in (SESSION_ENV, GQL_ENV, EXTRA_ENV):
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


# --- 403 の実測から入れた対策 ------------------------------------------------
#
# 2026-08-31: セッション Cookie だけで本番に投げて 403 が返った。note は
# double-submit cookie 方式で、Cookie とヘッダの両方に CSRF トークンが必要。

def test_XSRFのCookieは送らない(creds, net, store, monkeypatch):
    """**note.com に `XSRF-TOKEN` Cookie は存在しない**（オーナーのブラウザで
    確認）。存在しない Cookie を送ると、通らないときに原因の候補が増える。

    403 の原因を CSRF だと推測して Cookie に入れたのが誤りだった。
    実際の Cookie 一覧が推測に勝つ。"""
    monkeypatch.setenv(XSRF_ENV, "tok123")

    NotePublisher(store=store).publish(_article())

    assert "XSRF-TOKEN" not in net.calls[0]["cookies"]
    assert set(net.calls[0]["cookies"]) == {SESSION_COOKIE, GQL_COOKIE}


def test_ヘッダのXSRFはURLデコードする(creds, net, store, monkeypatch):
    """Cookie の値は percent-encoded。ブラウザ上の JS は Cookie を読んで
    デコードしてからヘッダに載せる。生のまま送ると照合に失敗する。"""
    monkeypatch.setenv(XSRF_ENV, "abc%3D%3D")

    NotePublisher(store=store).publish(_article())
    call = net.calls[0]

    assert call["headers"]["X-XSRF-TOKEN"] == "abc=="


def test_403は取り直すSecret名を案内する(creds, store, monkeypatch, caplog):
    """403 が出たとき何を登録すればいいか分からないと直せない。"""
    class Resp:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        NotePublisher(store=store).publish(_article())

    assert SESSION_ENV in caplog.text
    assert GQL_ENV in caplog.text
    assert EXTRA_ENV in caplog.text


def test_どのリクエストで落ちたかログに出る(creds, store, monkeypatch, caplog):
    """最初の実装では 403 が出ても新規作成・下書き保存・公開のどれで落ちたか
    判別できなかった。"""
    class Resp:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        result = NotePublisher(store=store).publish(_article())

    assert result["step"] == "新規作成"
    assert "新規作成" in caplog.text


def test_足りないCookieを後から足せる(creds, net, store, monkeypatch):
    """相手は非公式APIで、必要な Cookie が読み切れない。1つ増えるたびに
    コードを直す形にすると、そのたびに往復が発生する。"""
    monkeypatch.setenv(EXTRA_ENV, "fp=abc123; note_web_visitor_id=xyz")

    NotePublisher(store=store).publish(_article())
    cookies = net.calls[0]["cookies"]

    assert cookies["fp"] == "abc123"
    assert cookies["note_web_visitor_id"] == "xyz"
    # 必須の2つは残っている
    assert cookies[SESSION_COOKIE] and cookies[GQL_COOKIE]


def test_壊れたextraCookieは無視する(creds, net, store, monkeypatch):
    """コピペ由来の余分な `;` や空要素で落とさない。"""
    monkeypatch.setenv(EXTRA_ENV, "; =; fp=ok ;;")

    NotePublisher(store=store).publish(_article())

    assert net.calls[0]["cookies"]["fp"] == "ok"


# --- 403 が3回続いた末の実測 --------------------------------------------------

def test_ブラウザのUserAgentを送る(creds, net, store):
    """requests の既定（python-requests/2.x）だと 403 になる（実測）。
    Cookie を2つとも正しく送っても通らなかった。"""
    NotePublisher(store=store).publish(_article())
    ua = net.calls[0]["headers"]["User-Agent"]

    assert "Mozilla/5.0" in ua
    assert "python-requests" not in ua


def test_失敗時はレスポンスの中身をログに残す(creds, store, monkeypatch, caplog):
    """403 が note の API から来たのか、その前段の防御から来たのかは
    本文を見ないと区別できない。無いと毎回推測で次の手を決めることになる。"""
    class Resp:
        status_code = 403
        text = '{"error":"forbidden","message":"だめです"}'

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        NotePublisher(store=store).publish(_article())

    assert "forbidden" in caplog.text


def test_レスポンスのログは切り詰める(creds, store, monkeypatch, caplog):
    """HTML のエラーページが返ると、丸ごと出すとログが埋まる。"""
    class Resp:
        status_code = 403
        text = "<html>" + ("x" * 5000) + "</html>"

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        NotePublisher(store=store).publish(_article())

    for record in caplog.records:
        assert len(record.getMessage()) < 400


def test_レスポンスのログに認証情報を含めない(creds, store, monkeypatch, caplog):
    """このリポジトリは public。Actions のログも public に見える。"""
    class Resp:
        status_code = 403
        text = "forbidden"

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())

    with caplog.at_level(logging.DEBUG):
        NotePublisher(store=store).publish(_article())

    assert "SECRET_SESSION_VALUE" not in caplog.text
    assert "SECRET_GQL_TOKEN" not in caplog.text
