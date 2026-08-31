"""note への自動投稿（非公式API・ログインセッション）。

**なぜ非公式APIなのか。** note には記事投稿の公式 API が無い（2026年時点で
公開予定も未定）。オーナーが note を指定したため、ログイン済みセッションで
叩く経路を採る。公式APIではないので **note 側の内部仕様が変わると壊れる**。
その前提で、壊れたときに何が起きたか分かる形にしてある。

**認証情報の扱い。** 値はオーナーが GitHub Secrets に自分で登録し、こちらは
名前しか知らない（`CLAUDE.md` の運用原則）。ログにも出さない。このリポジトリは
public なので、値をファイルに書かない。

**実測できている仕様（2026-08-28、オーナーのブラウザで下書き保存したときの
リクエスト）。**

    POST https://note.com/api/v1/text_notes/draft_save?id=<id>&is_temp_saved=true
    payload:
      body: '<p name="{uuid}" id="{uuid}">テストです。</p>...'
      body_length: 6
      index: false
      is_lead_form: false
      name: "テスト"

`?id=` があるので、**この手前に「記事を新規作成して id をもらう」リクエストが
ある**。それと「公開する」リクエストは未取得。両方とも
`_MISSING_ENDPOINTS` に挙げてあり、揃うまで `publish()` は投稿しない。

**推測で埋めない理由。** 投稿先はオーナーの本番の note アカウントで、失敗が
下書きの汚れや誤公開として外に出る。エンドポイントを推測して当てにいくのは、
検証できないコードを本番に向けて発火させることと同じ。
"""
from __future__ import annotations

import logging
import os

import requests

from ..config import Config
from ..models import Article
from .note_body import to_note_html

logger = logging.getLogger(__name__)

# 必要な Secret 名。値ではなく名前だけをオーナーに伝える。
COOKIE_ENV = "NOTE_COOKIE"          # ログイン済みセッションの Cookie ヘッダ
XSRF_ENV = "NOTE_XSRF_TOKEN"        # CSRF トークン

API = "https://note.com/api"

# 実測できたリクエスト。
DRAFT_SAVE = f"{API}/v1/text_notes/draft_save"

# 未取得のリクエスト。埋まるまで投稿しない。
# キャプチャが来たらここだけ直せばよい形にしてある。
CREATE_NOTE = ""     # 記事を新規作成して id をもらう
PUBLISH_NOTE = ""    # 下書きを公開する

_MISSING_ENDPOINTS = {
    "新規作成": "CREATE_NOTE",
    "公開": "PUBLISH_NOTE",
}


class NotePublisher:
    """note の下書き保存・公開の薄いラッパー。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        pub = self.config.section("publishing")
        self.cookie = os.getenv(COOKIE_ENV, "").strip()
        self.xsrf = os.getenv(XSRF_ENV, "").strip()
        self.draft = bool(pub.get("note_draft", True))
        self.timeout = int(pub.get("note_timeout", 30))

    # ------------------------------------------------------------------
    def missing(self) -> list[str]:
        """未設定の Secret 名を返す。値は扱わない。"""
        return [name for name, value in ((COOKIE_ENV, self.cookie),
                                        (XSRF_ENV, self.xsrf)) if not value]

    def spec_gaps(self) -> list[str]:
        """まだ分かっていないリクエストの名前を返す。"""
        return [label for label, const in _MISSING_ENDPOINTS.items()
                if not globals()[const]]

    @property
    def available(self) -> bool:
        """投稿できる状態か。Secret が揃い、仕様の穴が無いこと。"""
        return not self.missing() and not self.spec_gaps()

    def _headers(self) -> dict[str, str]:
        """認証ヘッダ。**中身をログに出さない。**"""
        return {
            "Cookie": self.cookie,
            "X-XSRF-TOKEN": self.xsrf,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    def save_draft(self, note_id: str, title: str, body_html: str,
                   body_length: int) -> dict:
        """下書きを保存する。実測できているのはこのリクエストだけ。"""
        try:
            resp = requests.post(
                DRAFT_SAVE,
                params={"id": note_id, "is_temp_saved": "true"},
                json={
                    "body": body_html,
                    "body_length": body_length,
                    "index": False,
                    "is_lead_form": False,
                    "name": title,
                },
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            return _error(exc)
        return {"status": resp.status_code, "id": note_id}

    def publish(self, article: Article) -> dict:
        """記事を note に出す。出せないときは理由付きの dict を返す。

        例外を投げないのは、毎朝の cron が1回の障害で止まらないようにするため
        （collectors / llm / hatena と同じ方針）。
        """
        missing = self.missing()
        if missing:
            logger.warning("note へ投稿しません。未設定の Secret: %s",
                           ", ".join(missing))
            return {"skipped": "secrets_missing", "missing": missing}

        gaps = self.spec_gaps()
        if gaps:
            # 推測で叩かない。当てにいった結果が本番アカウントの下書きの汚れや
            # 誤公開として外に出る。
            logger.warning("note の仕様が未確定なので投稿しません。"
                           "未取得のリクエスト: %s", "・".join(gaps))
            return {"skipped": "spec_missing", "gaps": gaps}

        body_html, body_length = to_note_html(article.body_markdown)
        return {"skipped": "not_implemented",
                "body_length": body_length,
                "note": "新規作成と公開のリクエストが埋まったらここを実装する"}


def _error(exc: requests.RequestException) -> dict:
    """失敗を dict にする。**認証情報を含めない。**

    requests の例外は url を持ち、url にトークンが乗る API もある。ここでは
    ステータスと種類だけを残す。
    """
    status = getattr(exc.response, "status_code", 0)
    if status in (401, 403):
        logger.error("note の認証に失敗しました（%s）。%s と %s を"
                     "取り直してください。ログインし直すと変わります。",
                     status, COOKIE_ENV, XSRF_ENV)
    else:
        logger.error("note への投稿に失敗しました: %s", type(exc).__name__)
    return {"error": type(exc).__name__, "status": status}
