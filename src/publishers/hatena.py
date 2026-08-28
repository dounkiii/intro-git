"""はてなブログへの自動投稿（AtomPub）。

**なぜ note ではないのか。** note には記事投稿の公式 API が無い（2026年時点で
公開予定も未定）。自動投稿している事例はすべて、ログイン済みブラウザの
セッション Cookie を使う非公式 API で、

  - オーナーの note ログイン情報をこちら側で預かることになる
  - note 側の内部仕様が変わるたびに壊れる

の2点から採用しない。認証情報を預からない方針は `CLAUDE.md` に書いた運用原則。

はてなブログ AtomPub は**公式 API**で、認証はパスワードではなく **API キー**
（WSSE）。オーナーは Secret 名だけ登録すればよく、こちら側は値を見ない。

  https://developer.hatena.ne.jp/ja/documents/blog/apis/atom/

投稿は既定で**下書き**にしている。承認ゲート（`/approve`）を人が通した後とは
いえ、新しい外部連携が初回から公開してしまうと、書式崩れや投稿先違いに
気づく前に世に出る。1本目を確認したら `publishing.hatena_draft` を false に
すれば、以後は承認するだけで公開される。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import requests

from ..config import Config
from ..models import Article

logger = logging.getLogger(__name__)

ENDPOINT = "https://blog.hatena.ne.jp/{user}/{blog}/atom/entry"

# 必要な Secret 名。値ではなく名前だけをオーナーに伝える。
USER_ENV = "HATENA_USER_ID"
BLOG_ENV = "HATENA_BLOG_ID"
KEY_ENV = "HATENA_API_KEY"


def _wsse(user: str, api_key: str) -> str:
    """WSSE 認証ヘッダを組む。

    nonce は毎回変える（使い回すとリプレイとして弾かれる）。
    """
    nonce = secrets.token_bytes(20)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha1(nonce + created.encode() + api_key.encode()).digest()
    return (
        'UsernameToken Username="{u}", PasswordDigest="{d}", '
        'Nonce="{n}", Created="{c}"'.format(
            u=user,
            d=base64.b64encode(digest).decode(),
            n=base64.b64encode(nonce).decode(),
            c=created,
        )
    )


def build_entry(article: Article, author: str, draft: bool,
                categories: list[str] | None = None) -> str:
    """AtomPub の投稿 XML を組む。

    本文は Markdown のまま送る（はてなブログ側の編集モードが Markdown なら
    そのまま解釈される）。タイトルと本文は必ずエスケープする。記事は LLM が
    書くので、`<` や `&` が入っても XML を壊さないようにする。
    """
    cats = "".join(
        f'<category term="{escape(c)}" />' for c in (categories or []))
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<entry xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:app="http://www.w3.org/2007/app">'
        f"<title>{escape(article.title)}</title>"
        f"<author><name>{escape(author)}</name></author>"
        f'<content type="text/plain">{escape(article.body_markdown)}</content>'
        f"{cats}"
        "<app:control>"
        f"<app:draft>{'yes' if draft else 'no'}</app:draft>"
        "</app:control>"
        "</entry>"
    )


class HatenaPublisher:
    """はてなブログ AtomPub の薄いラッパー。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        pub = self.config.section("publishing")
        self.user = os.getenv(USER_ENV, "").strip()
        self.blog = os.getenv(BLOG_ENV, "").strip()
        self.api_key = os.getenv(KEY_ENV, "").strip()
        self.draft = bool(pub.get("hatena_draft", True))
        self.categories: list[str] = pub.get("hatena_categories") or []
        self.timeout = int(pub.get("hatena_timeout", 30))

    @property
    def available(self) -> bool:
        """3つの Secret が揃っているか。欠けていれば投稿しない。"""
        return bool(self.user and self.blog and self.api_key)

    def missing(self) -> list[str]:
        """未設定の Secret 名を返す。オーナーへの案内に使う（値は扱わない）。"""
        return [name for name, value in (
            (USER_ENV, self.user), (BLOG_ENV, self.blog), (KEY_ENV, self.api_key)
        ) if not value]

    def publish(self, article: Article) -> dict:
        """記事を投稿する。投稿できないときは理由付きの dict を返す。

        例外を投げないのは、毎朝の cron が1回の障害で止まらないようにするため
        （collectors / llm と同じ方針）。
        """
        if not self.available:
            logger.warning("はてなブログへ投稿しません。未設定の Secret: %s",
                           ", ".join(self.missing()))
            return {"skipped": "secrets_missing", "missing": self.missing()}

        body = build_entry(article, author=self.user, draft=self.draft,
                           categories=self.categories)
        try:
            resp = requests.post(
                ENDPOINT.format(user=self.user, blog=self.blog),
                data=body.encode("utf-8"),
                headers={
                    "X-WSSE": _wsse(self.user, self.api_key),
                    "Content-Type": "application/atom+xml; charset=utf-8",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", 0)
            if status == 401:
                logger.error("はてなブログの認証に失敗しました（401）。"
                             "%s と %s が正しいか確認してください。",
                             USER_ENV, KEY_ENV)
            else:
                logger.error("はてなブログへの投稿に失敗しました: %s", exc)
            return {"error": str(exc), "status": status}

        url = _entry_url(resp.text)
        logger.info("はてなブログに投稿しました（%s）: %s",
                    "下書き" if self.draft else "公開", url or "(URL不明)")
        return {"url": url, "draft": self.draft, "status": resp.status_code}


def _entry_url(xml: str) -> str:
    """レスポンスから記事の URL を拾う。取れなくても投稿は成功している。"""
    import re

    m = re.search(r'<link[^>]+rel="alternate"[^>]+href="([^"]+)"', xml)
    return m.group(1) if m else ""
