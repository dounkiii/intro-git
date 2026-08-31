"""note への自動投稿（非公式API・ログインセッション）。

**なぜ非公式APIなのか。** note には記事投稿の公式 API が無い（2026年時点で
公開予定も未定）。オーナーが note を指定したため、ログイン済みセッションで
叩く経路を採る。公式APIではないので **note 側の内部仕様が変わると壊れる**。

## 仕様の根拠（どこまで裏付けがあるか）

推測で本番アカウントに投げないために、根拠の強さを分けて書く。

**実測（オーナーのブラウザで下書き保存したときのリクエスト、2026-08-28）**

    POST /api/v1/text_notes/draft_save?id=<id>&is_temp_saved=true
    {body, body_length, index: false, is_lead_form: false, name}

**公開実装3件で一致（2026-08-31 に GitHub 上で確認）**

    新規作成  POST /api/v1/text_notes           {"template_key": null}
              → レスポンスから id / key / slug
    公開      PUT  /api/v1/text_notes/{id}      status="published", price=0

  - tpyhon/-juggler_predictor `scripts/weekly_report.py`（Python）
  - i0switch/ThreadsOS `src/adapters/note-api/index.ts`（TypeScript）
  - Mr-SuperInsane/NoteClient2 `NoteClient2/client.py`（Python）

3件は互いに独立で、**実測できた draft_save の形が3件とも一致している**ため、
残り2本も同じ資料から採って妥当と判断した。ただし**こちらで実行しての確認は
できていない**（この実行環境から note.com は遮断されている）。だから
**既定は下書き**にしてある。1本目をオーナーが note の画面で見て確認する。

`body_length` は**実測値に合わせて本文の文字数**（タグを除く）にしている。
公開実装2件は `len(body_html)` を送っていたが、note のエディタ自身が送って
いたのは「テストです。」6文字に対して 6 だった。**推測より実測を採る。**

## 認証情報の扱い

値はオーナーが GitHub Secrets に自分で登録し、こちらは名前しか知らない
（`CLAUDE.md` の運用原則）。ログにも出さない。このリポジトリは public なので、
値をファイルに書かない。**ログインし直すと Cookie が変わる**ので、投稿が
401/403 で止まったら差し替えが必要。これが非公式APIを使う代償。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from pathlib import Path

import requests

from ..config import DATA_DIR, Config
from ..models import Article
from .note_body import to_note_html

logger = logging.getLogger(__name__)

# 必要な Secret 名。値ではなく名前だけをオーナーに伝える。
#
# **2026-08-31 の実測でここを直した。** 当初は `_note_session_v5` だけを送って
# 403 になり、原因を CSRF トークン（`XSRF-TOKEN` Cookie）だと考えた。しかし
# オーナーのブラウザを確認すると **note.com に `XSRF-TOKEN` Cookie は存在しない**。
# 実際にあるのは6つで、うち認証に効くのは `note_gql_auth_token`（JWT）だった。
# **推測した対策より、実際の Cookie 一覧が勝つ。**
SESSION_ENV = "NOTE_SESSION_V5"          # Cookie `_note_session_v5`（必須）
GQL_ENV = "NOTE_GQL_AUTH_TOKEN"          # Cookie `note_gql_auth_token`（必須）
XSRF_ENV = "NOTE_XSRF_TOKEN"             # 任意。ヘッダにだけ載せる
# 上の2つで足りなかったときの逃げ道。`k=v; k=v` の生の形で渡す。
# 仕様が読めない相手なので、Cookie を1つ増やすたびにコードを直す形にしない。
EXTRA_ENV = "NOTE_EXTRA_COOKIES"

API = "https://note.com/api/v1/text_notes"
SESSION_COOKIE = "_note_session_v5"
GQL_COOKIE = "note_gql_auth_token"

# ブラウザの User-Agent。
#
# **これを送っていなかったせいで 403 が続いた（2026-08-31 実測）。** requests の
# 既定は `python-requests/2.x` で、note（またはその前段の防御）はそれを弾く。
# Cookie を2つとも正しく送っても通らなかった。参考にした公開実装は
# 「User-Agent（標準ブラウザUA）」を必須として挙げていたのに、こちらが
# 落としていた。**資料に書いてあるヘッダを省略しない。**
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0.0.0 Safari/537.36")

# 作成した note の id を覚えておく場所。
# **毎晩の実行で同じ記事の下書きを作り直さないため。** 持たないと、承認済みの
# 記事1本につき下書きが毎日1件増えていく。
STATE_PATH = DATA_DIR / "publish" / "note_ids.json"


class NoteIdStore:
    """記事ID → note の id / key / slug の対応を覚える。"""

    def __init__(self, path: Path = STATE_PATH):
        self.path = path

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 壊れていても投稿を止めない。作り直す（下書きが1件増えるだけ）。
            logger.warning("note の ID 台帳が読めません: %s", self.path)
            return {}

    def get(self, item_id: str) -> dict | None:
        return self.load().get(item_id)

    def put(self, item_id: str, note: dict) -> None:
        data = self.load()
        data[item_id] = note
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class NotePublisher:
    """note の新規作成・下書き保存・公開。"""

    def __init__(self, config: Config | None = None,
                 store: NoteIdStore | None = None):
        self.config = config or Config.load()
        pub = self.config.section("publishing")
        self.session_cookie = os.getenv(SESSION_ENV, "").strip()
        self.gql_token = os.getenv(GQL_ENV, "").strip()
        self.xsrf = os.getenv(XSRF_ENV, "").strip()
        self.extra_cookies = os.getenv(EXTRA_ENV, "").strip()
        self.draft = bool(pub.get("note_draft", True))
        self.timeout = int(pub.get("note_timeout", 30))
        self.hashtags: list[str] = pub.get("hashtags") or []
        self.store = store or NoteIdStore()

    # ------------------------------------------------------------------
    def missing(self) -> list[str]:
        """未設定の Secret 名を返す。値は扱わない。"""
        return [name for name, value in ((SESSION_ENV, self.session_cookie),
                                        (GQL_ENV, self.gql_token))
                if not value]

    @property
    def available(self) -> bool:
        return not self.missing()

    def _headers(self) -> dict[str, str]:
        """リクエストヘッダ。**中身をログに出さない。**

        `Origin` / `Referer` を editor.note.com にするのは、公開実装3件が
        揃ってそうしていたため。note 側が参照元を見ている可能性がある。

        `X-XSRF-TOKEN` には **URL デコードした値**を入れる。Cookie に入っている
        値は percent-encoded（`=` が `%3D` など）で、ブラウザ上の JS は Cookie を
        読んでデコードしてからヘッダに載せる。生のまま送ると照合に失敗する。
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://editor.note.com",
            "Referer": "https://editor.note.com/",
        }
        if self.xsrf:
            headers["X-XSRF-TOKEN"] = urllib.parse.unquote(self.xsrf)
        return headers

    def _cookies(self) -> dict[str, str]:
        """Cookie。**セッションだけでは 403 になる（実測）。**

        ブラウザが note.com に持っている Cookie は6つで、認証に効くのは
        `_note_session_v5` と `note_gql_auth_token`（JWT）。前者だけ送って
        403 が返ったので、両方送る。

        残り4つ（`_vid_v1` / `_vid_v2` / `fp` / `note_web_visitor_id`）は
        計測・フィングープリント用に見えるので送らない。それでも通らない
        場合に備えて `NOTE_EXTRA_COOKIES` で足せるようにしてある。
        """
        cookies = {SESSION_COOKIE: self.session_cookie,
                   GQL_COOKIE: self.gql_token}
        for pair in self.extra_cookies.split(";"):
            name, _, value = pair.partition("=")
            if name.strip() and value.strip():
                cookies[name.strip()] = value.strip()
        return cookies

    def _request(self, method: str, url: str, payload: dict,
                 step: str = "") -> dict:
        """1回のリクエスト。例外を投げず dict を返す。

        毎朝の cron が1回の障害で止まらないようにするため
        （collectors / llm / hatena と同じ方針）。

        `step` を渡すのは、**どのリクエストで落ちたかログから分かるように**
        するため。最初の実装では 403 が出ても新規作成・下書き保存・公開の
        どれで落ちたのか判別できなかった。
        """
        try:
            resp = requests.request(
                method, url, json=payload, headers=self._headers(),
                cookies=self._cookies(), timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            return _error(exc, step)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return {"status": resp.status_code, "data": body.get("data", body)}

    # ------------------------------------------------------------------
    def create_note(self) -> dict:
        """空の記事を作って id / key / slug をもらう。

        下書き保存のURLに `?id=` が必要なので、これが最初に来る。
        """
        result = self._request("POST", API, {"template_key": None},
                               step="新規作成")
        if "error" in result:
            return result
        data = result.get("data") or {}
        note_id = data.get("id")
        if not note_id:
            logger.error("note の新規作成でIDが返りませんでした。"
                         "note 側の仕様が変わった可能性があります。")
            return {"error": "no_id", "status": result.get("status", 0)}
        return {"id": str(note_id), "key": data.get("key", ""),
                "slug": data.get("slug", "")}

    def save_draft(self, note_id: str, title: str, body_html: str,
                   body_length: int) -> dict:
        """下書きを保存する。**この形だけは実測で確認できている。**"""
        return self._request(
            "POST",
            f"{API}/draft_save?id={note_id}&is_temp_saved=true",
            {
                "body": body_html,
                "body_length": body_length,
                "index": False,
                "is_lead_form": False,
                "name": title,
            },
            step="下書き保存",
        )

    def publish_note(self, note: dict, title: str, body_html: str,
                     body_length: int) -> dict:
        """下書きを公開する。無料記事なので price は 0。

        `free_body` に本文を入れるのは、有料記事の「無料で読める部分」の
        フィールドを全文に使う形（公開実装3件が揃ってそうしている）。
        """
        return self._request(
            "PUT",
            f"{API}/{note['id']}",
            {
                "name": title,
                "free_body": body_html,
                "body_length": body_length,
                "status": "published",
                "price": 0,
                "slug": note.get("slug") or note["id"],
                "index": True,
                "is_lead_form": False,
                "circle_permissions": [],
                "author_ids": [],
                "exclude_from_creator_top": False,
                "hashtags": [{"name": t.lstrip("#")} for t in self.hashtags],
            },
            step="公開",
        )

    # ------------------------------------------------------------------
    def publish(self, article: Article, item_id: str = "") -> dict:
        """記事を note に出す。出せないときは理由付きの dict を返す。

        既定は**下書き**（`publishing.note_draft`）。非公式APIで、こちらでは
        実行して確かめられていないので、1本目はオーナーが note の画面で
        書式を確認する。確認できたら config で false にすれば以後は公開される。
        """
        missing = self.missing()
        if missing:
            logger.warning("note へ投稿しません。未設定の Secret: %s",
                           ", ".join(missing))
            return {"skipped": "secrets_missing", "missing": missing}

        title = article.title
        body_html, body_length = to_note_html(article.body_markdown)

        key = item_id or title
        note = self.store.get(key)
        if note is None:
            note = self.create_note()
            if "error" in note:
                return note
            # **作成できた時点で覚える。** ここで落ちると、次回また新しい
            # 下書きが作られて増えていく。
            self.store.put(key, note)
            logger.info("note の下書きを作成しました（id=%s）", note["id"])

        saved = self.save_draft(note["id"], title, body_html, body_length)
        if "error" in saved:
            return saved

        if self.draft:
            logger.info("note に下書き保存しました（id=%s）。"
                        "内容を確認したら publishing.note_draft を false に。",
                        note["id"])
            return {"note_id": note["id"], "draft": True,
                    "url": _draft_url(note), "body_length": body_length}

        published = self.publish_note(note, title, body_html, body_length)
        if "error" in published:
            return published

        logger.info("note に公開しました（id=%s）", note["id"])
        return {"note_id": note["id"], "draft": False,
                "url": _public_url(published.get("data") or {}, note),
                "body_length": body_length}


def _draft_url(note: dict) -> str:
    """編集画面のURL。オーナーが下書きを確認するために出す。"""
    return f"https://editor.note.com/notes/{note.get('key') or note['id']}/edit/"


def _public_url(data: dict, note: dict) -> str:
    """公開後のURL。レスポンスに無ければ空（投稿自体は成功している）。"""
    key = data.get("key") or note.get("key")
    user = data.get("user", {}).get("urlname") if isinstance(
        data.get("user"), dict) else ""
    if user and key:
        return f"https://note.com/{user}/n/{key}"
    return ""


def _body_snippet(resp) -> str:
    """レスポンス本文の先頭だけを返す。

    **原因の切り分けに必要。** 403 が note の API から来たのか、その前段の
    防御（Cloudflare など）から来たのかは、本文を見ないと区別できない。
    2026-08-31 は 403 が3回続き、毎回「次に何を疑うか」を推測で決めていた。

    送った Cookie やヘッダは含めない（このリポジトリは public）。長さも切る。
    """
    text = getattr(resp, "text", "") or ""
    return " ".join(text[:200].split())


def _error(exc: requests.RequestException, step: str = "") -> dict:
    """失敗を dict にする。**認証情報を含めない。**

    requests の例外は url を持つ。ここではステータスと例外の種類だけを残す。
    `step` を出すのは、どのリクエストで落ちたかが分からないと直せないため。
    """
    status = getattr(exc.response, "status_code", 0)
    where = f"（{step}）" if step else ""
    snippet = _body_snippet(exc.response) if exc.response is not None else ""
    if snippet:
        logger.error("note のレスポンス（先頭200文字）: %s", snippet)
    if status in (401, 403):
        logger.error("note の認証に失敗しました（%s）%s。%s と %s を"
                     "取り直してください。note でログインし直すと値が変わります。"
                     "それでも通らない場合は %s に残りの Cookie を足してください。",
                     status, where, SESSION_ENV, GQL_ENV, EXTRA_ENV)
    elif status == 0:
        logger.error("note に接続できませんでした%s: %s",
                     where, type(exc).__name__)
    else:
        logger.error("note への投稿に失敗しました（HTTP %s）%s。note 側の仕様が"
                     "変わった可能性があります。", status, where)
    return {"error": type(exc).__name__, "status": status, "step": step}
