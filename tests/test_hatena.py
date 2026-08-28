"""はてなブログ投稿のテスト。

一番守りたいのは「認証情報を預からない」ことと「1回の障害で毎朝の cron を
止めない」こと。どちらもこのプロジェクトで繰り返し決めてきた方針。
"""
import base64
import hashlib

import pytest
import requests

from src.models import Article
from src.publishers.hatena import (BLOG_ENV, KEY_ENV, USER_ENV,
                                   HatenaPublisher, build_entry)


def _article(**kw) -> Article:
    base = dict(topic_category="tax", title="タイトル",
                body_markdown="本文です。", monetization_route="なし")
    base.update(kw)
    return Article(**base)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv(USER_ENV, "someuser")
    monkeypatch.setenv(BLOG_ENV, "someuser.hatenablog.com")
    monkeypatch.setenv(KEY_ENV, "secret-api-key")


def test_Secretが欠けていたら投稿しない(monkeypatch):
    """未設定のまま叩くと 401 が返るだけなので、手前で止めて名前を案内する。"""
    for name in (USER_ENV, BLOG_ENV, KEY_ENV):
        monkeypatch.delenv(name, raising=False)

    result = HatenaPublisher().publish(_article())

    assert result["skipped"] == "secrets_missing"
    assert set(result["missing"]) == {USER_ENV, BLOG_ENV, KEY_ENV}


def test_欠けているSecretの名前だけを返す(monkeypatch):
    """オーナーに伝えるのは Secret 名まで。値は扱わない。"""
    monkeypatch.setenv(USER_ENV, "someuser")
    monkeypatch.delenv(BLOG_ENV, raising=False)
    monkeypatch.setenv(KEY_ENV, "secret-api-key")

    missing = HatenaPublisher().missing()

    assert missing == [BLOG_ENV]
    # 値そのものが漏れていない
    assert "secret-api-key" not in " ".join(missing)


def test_通信が失敗しても例外を投げない(creds, monkeypatch):
    """毎朝の cron を1回の障害で止めない（collectors / llm と同じ方針）。"""
    def boom(*a, **k):
        raise requests.ConnectionError("接続できません")

    monkeypatch.setattr(requests, "post", boom)

    result = HatenaPublisher().publish(_article())

    assert "error" in result


def test_認証エラーは直すべきSecret名を出す(creds, monkeypatch, caplog):
    """401 のとき「どのキーを見ればいいか」が分からないと直せない。"""
    class Resp:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError("401", response=self)

    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())

    with caplog.at_level("ERROR"):
        HatenaPublisher().publish(_article())

    assert KEY_ENV in caplog.text


def test_投稿XMLはエスケープされる():
    """記事は LLM が書くので < や & が入りうる。XML を壊さないこと。"""
    xml = build_entry(_article(title="A & B <危険>",
                               body_markdown="5 < 10 & 3 > 1"),
                      author="u", draft=True)

    assert "A &amp; B &lt;危険&gt;" in xml
    assert "5 &lt; 10 &amp; 3 &gt; 1" in xml


def test_既定は下書き():
    """新しい外部連携が初回から公開すると、書式崩れに気づく前に世に出る。"""
    assert "<app:draft>yes</app:draft>" in build_entry(
        _article(), author="u", draft=True)
    assert "<app:draft>no</app:draft>" in build_entry(
        _article(), author="u", draft=False)


def test_設定で公開に切り替えられる(creds, monkeypatch):
    """1本目を確認したら config 1行で以後は自動公開になること。"""
    from src.config import Config

    config = Config.load()
    config.section("publishing")["hatena_draft"] = False

    assert HatenaPublisher(config).draft is False


def test_WSSEのnonceは毎回変わる(creds):
    """使い回すとリプレイとして弾かれる。"""
    from src.publishers.hatena import _wsse

    assert _wsse("u", "k") != _wsse("u", "k")


def test_WSSEのダイジェストが仕様どおり(creds):
    """base64(sha1(nonce + created + api_key)) であること。"""
    import re

    from src.publishers.hatena import _wsse

    header = _wsse("someuser", "secret-api-key")
    digest = re.search(r'PasswordDigest="([^"]+)"', header).group(1)
    nonce = base64.b64decode(re.search(r'Nonce="([^"]+)"', header).group(1))
    created = re.search(r'Created="([^"]+)"', header).group(1)

    expected = base64.b64encode(
        hashlib.sha1(nonce + created.encode() + b"secret-api-key").digest()
    ).decode()
    assert digest == expected


def test_承認したら投稿まで行く(creds, monkeypatch, tmp_path):
    """承認 → 記事書き出し → 投稿 が1回で通ること。手でコピペしない。"""
    sent: dict = {}

    class Resp:
        status_code = 201
        text = '<link rel="alternate" href="https://example.com/entry/1" />'

        def raise_for_status(self):
            return None

    def fake_post(url, data=None, headers=None, timeout=None):
        sent["url"] = url
        sent["body"] = data.decode("utf-8")
        sent["auth"] = headers.get("X-WSSE", "")
        return Resp()

    monkeypatch.setattr(requests, "post", fake_post)

    result = HatenaPublisher().publish(_article(title="ふるさと納税の上限"))

    assert result["url"] == "https://example.com/entry/1"
    assert "someuser.hatenablog.com" in sent["url"]
    assert "ふるさと納税の上限" in sent["body"]
    assert "UsernameToken" in sent["auth"]
    # API キーそのものは送られない（ダイジェストのみ）
    assert "secret-api-key" not in sent["auth"]


def test_投稿するワークフローにSecretが渡っている():
    """#6 の再発防止。Secrets を登録しても env に書き忘れると、
    ランナーでは常に空になり「登録したのに動かない」になる。"""
    import pathlib

    text = pathlib.Path(".github/workflows/approve-command.yml").read_text(
        encoding="utf-8")
    publish_step = text[text.index("publish --approved") - 2000:]

    for name in (USER_ENV, BLOG_ENV, KEY_ENV):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in text, name
        assert name in publish_step, f"{name} が publish ステップに渡っていない"
