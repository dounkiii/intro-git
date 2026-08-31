"""note 投稿のテスト。

一番守りたいのは3つ。

1. **仕様が分かっていない状態で本番に発火しない。** 投稿先はオーナーの本番の
   note アカウントで、推測で当てにいった失敗が下書きの汚れや誤公開として
   外に出る
2. **認証情報を漏らさない。** このリポジトリは public
3. **1回の障害で毎朝の cron を止めない**
"""
import logging

import pytest
import requests

from src.models import Article
from src.publishers.note import (COOKIE_ENV, DRAFT_SAVE, XSRF_ENV,
                                 NotePublisher)


def _article(**kw) -> Article:
    base = dict(topic_category="tax", title="タイトル",
                body_markdown="本文です。", monetization_route="なし")
    base.update(kw)
    return Article(**base)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv(COOKIE_ENV, "session=SECRET_COOKIE_VALUE")
    monkeypatch.setenv(XSRF_ENV, "SECRET_XSRF_VALUE")


def test_Secretが欠けていたら投稿しない(monkeypatch):
    for name in (COOKIE_ENV, XSRF_ENV):
        monkeypatch.delenv(name, raising=False)

    result = NotePublisher().publish(_article())

    assert result["skipped"] == "secrets_missing"
    assert set(result["missing"]) == {COOKIE_ENV, XSRF_ENV}


def test_欠けているSecretの名前だけを返す(monkeypatch):
    """オーナーに伝えるのは Secret 名まで。値は扱わない。"""
    monkeypatch.setenv(COOKIE_ENV, "session=SECRET_COOKIE_VALUE")
    monkeypatch.delenv(XSRF_ENV, raising=False)

    missing = NotePublisher().missing()

    assert missing == [XSRF_ENV]
    assert "SECRET_COOKIE_VALUE" not in " ".join(missing)


def test_仕様が未確定なら本番に発火しない(creds):
    """これが本題。note には公式APIが無く、新規作成と公開のリクエストは
    まだ実測できていない。埋まっていないのに叩くと、推測を本番アカウントに
    向けて試すことになる。"""
    result = NotePublisher().publish(_article())

    assert result["skipped"] == "spec_missing"
    assert set(result["gaps"]) == {"新規作成", "公開"}


def test_未取得のリクエストが名前で分かる(creds):
    """何が足りないか分からないと、キャプチャを頼む相手に説明できない。"""
    gaps = NotePublisher().spec_gaps()

    assert "新規作成" in gaps and "公開" in gaps


def test_穴が埋まるまで投稿可能にならない(creds):
    assert NotePublisher().available is False


def test_下書き保存のpayloadが実測どおり(creds, monkeypatch):
    """基準はオーナーのブラウザで実際に下書き保存したときのリクエスト。

    body / body_length / index / is_lead_form / name の5つで、
    クエリに id と is_temp_saved が付く。
    """
    sent: dict = {}

    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_post(url, params=None, json=None, headers=None, timeout=None):
        sent.update(url=url, params=params, json=json, headers=headers)
        return Resp()

    monkeypatch.setattr(requests, "post", fake_post)

    NotePublisher().save_draft("177206277", "テスト",
                               '<p name="u0" id="u0">テストです。</p>', 6)

    assert sent["url"] == DRAFT_SAVE
    assert sent["params"] == {"id": "177206277", "is_temp_saved": "true"}
    assert set(sent["json"]) == {"body", "body_length", "index",
                                 "is_lead_form", "name"}
    assert sent["json"]["name"] == "テスト"
    assert sent["json"]["body_length"] == 6
    assert sent["json"]["index"] is False
    assert sent["json"]["is_lead_form"] is False


def test_通信が失敗しても例外を投げない(creds, monkeypatch):
    """毎朝の cron を1回の障害で止めない。"""
    def boom(*a, **k):
        raise requests.ConnectionError("接続できません")

    monkeypatch.setattr(requests, "post", boom)

    result = NotePublisher().save_draft("1", "t", "<p></p>", 0)

    assert "error" in result


def test_認証エラーは取り直すSecret名を出す(creds, monkeypatch, caplog):
    """note の Cookie はログインし直すと変わる。401 のとき何を差し替えれば
    いいか分からないと直せない。"""
    class Resp:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError("401", response=self)

    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        NotePublisher().save_draft("1", "t", "<p></p>", 0)

    assert COOKIE_ENV in caplog.text
    assert XSRF_ENV in caplog.text


def test_認証情報をログに出さない(creds, monkeypatch, caplog):
    """このリポジトリは public。Actions のログも public に見える。"""
    class Resp:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError("403", response=self)

    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())

    with caplog.at_level(logging.DEBUG):
        result = NotePublisher().save_draft("1", "t", "<p></p>", 0)

    blob = caplog.text + repr(result)
    assert "SECRET_COOKIE_VALUE" not in blob
    assert "SECRET_XSRF_VALUE" not in blob


def test_既定は下書き(creds):
    """新しい外部連携が初回から公開すると、書式崩れに気づく前に世に出る。
    しかも note は公式APIではないので、崩れ方が読めない。"""
    assert NotePublisher().draft is True


def test_設定で公開に切り替えられる(creds):
    """1本目を確認したら config 1行で以後は自動公開になること。"""
    from src.config import Config

    config = Config.load()
    config.section("publishing")["note_draft"] = False

    assert NotePublisher(config).draft is False


def test_本文はMarkdownではなくnoteのHTMLで送る(creds):
    """note の下書き保存APIは Markdown を受け取らない。"""
    import inspect

    from src.publishers import note

    src = inspect.getsource(note.NotePublisher.publish)

    assert "to_note_html" in src
