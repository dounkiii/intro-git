# X 公式 MCP（xmcp）を Claude Code につなぐ

**目的は「ツイートを実際に読む」こと。** いま探索も制作も固定のサンプルから
作られていて、実データを1件も読んでいない（`docs/RESEARCH_SYSTEM.md` の
実装バグ台帳 #12）。xmcp はその穴のうち「オーナーが対話で X を読む」側を埋める。

---

## 最初に: 何が変わって、何が変わらないか

| | xmcp を入れると |
|---|---|
| オーナーの PC の Claude Code | **変わる。** 対話の中で X を検索・取得できる |
| 毎晩の GitHub Actions（daily-scout / daily-generate） | **変わらない。** MCP を使っていない |

**毎晩のパイプラインを実データにするのは MCP ではなく Secret です。**
`X_BEARER_TOKEN` を GitHub の Secrets に入れるまで、探索は
`data/scout/sample_candidates.json` の2件、制作は `data/sample_tweets.json` の
4件を読み続けます。

ただし**両方とも同じ X Developer アプリから取れる**ので、作業は1回で済みます。
xmcp の `.env` にも `X_BEARER_TOKEN` が必須です（公式 README が
"required for this setup" と明記）。

## このセッション（クラウド）からは設定できません

実測（2026-09-01、この環境から `curl`）:

```
api.twitter.com:443 — connect_rejected
api.x.com:443       — connect_rejected
x.com:443           — connect_rejected
```

egress プロキシが X 系のドメインを塞いでいます。**note.com と同じ状況**で、
Claude Code のクラウドセッションからは xmcp を動かしても呼び出しが全部落ちます。
`xmcp` は `http://127.0.0.1:8000/mcp` を待ち受けるローカルサーバなので、
そもそも「オーナーの PC の 127.0.0.1」とこのコンテナの 127.0.0.1 は別物です。

**設定はオーナーの PC の Claude Code で行ってください。**

---

## 前提

- Python 3.9+ が入った PC（スマホだけでは無理。ここは note と同じ制約）
- **X Developer Platform のアプリ**（Consumer Key / Secret と Bearer Token が取れる）
- **X API の従量課金（Pay-per-use）クレジット。** 無料枠は新規提供が止まっており、
  読み取りにも課金が要ります（`docs/RESEARCH_SYSTEM.md` の実測で月$30前後、
  最小のお試しは$5前後という報告あり。**この金額はこちらで確認していません**）

## 手順（公式 README `xdevplatform/xmcp` に基づく・こちらで実行しての確認はしていない）

```bash
git clone https://github.com/xdevplatform/xmcp
cd xmcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env          # ここに値を書く。リポジトリには絶対に入れない
```

`.env` に必須の3つ:

```
X_OAUTH_CONSUMER_KEY
X_OAUTH_CONSUMER_SECRET
X_BEARER_TOKEN
```

X Developer App 側に**コールバック URL を登録**します（既定値のままなら）:

```
http://127.0.0.1:8976/oauth/callback
```

起動:

```bash
python server.py            # 既定で http://127.0.0.1:8000/mcp
```

起動時にブラウザが開いて OAuth1 の同意を求めます。トークンは
**プロセスが生きている間だけメモリに載る**（ファイルに残らない）。

Claude Code に登録:

```bash
claude mcp add --transport http --scope user xmcp http://127.0.0.1:8000/mcp
```

> `MCP_PORT` を変えたらこの URL も合わせること。ネット上の記事は 8001 番を
> 書いているものがありますが、**公式 README の既定は 8000** です。

---

## 必ず読み取り専用に絞ること（承認ゲートを迂回させない）

xmcp は X API の OpenAPI をそのままツール化するので、**何もしないと
`createPosts` / `deletePosts` / DM 系まで生えます。** このプロジェクトは
「投稿の前に人間が `/approve` を押す」ことを法務リスクの最後の一段として
設計しています（`CLAUDE.md`「承認ゲートは自動化しない」）。LLM が直接
ポストできる口を開けると、その設計が意味を失います。

`.env` に allowlist を書いて起動時に絞ってください。**読むだけなら:**

```
X_API_TOOL_ALLOWLIST=searchPostsRecent,getPostsCountsRecent,getUsersByUsername,getTrendsByWoeid
```

allowlist は**起動時**に効きます。変えたらサーバを再起動すること。

`searchPostsRecent` に渡すクエリは `config.yaml` の `collection.queries` を
そのまま使えます（`(確定申告 OR インボイス ...) lang:ja -is:retweet`）。
探索側は `scout.discovery_queries`。

## 認証情報の扱い

- **このリポジトリは public。`.env` も Key も絶対にコミットしない**
- **チャットに貼らない。** こちらが必要なのは Secret 名と審査状況までで、
  値はオーナー側だけで管理してください（`CLAUDE.md`「認証情報はチャットに要求しない」）
- 万一貼ってしまったら、X Developer Portal で **regenerate** してください

## つまずきポイント

| 症状 | 原因と対処 |
|---|---|
| `claude mcp add` は通るのにツールが出ない | サーバが起動していない。`python server.py` を別ターミナルで動かしたまま使う |
| 起動時にブラウザが開かない / コールバックで固まる | X Developer App にコールバック URL が未登録。`X_OAUTH_CALLBACK_PORT` と一致させる |
| 401 / 403 | Bearer Token かアプリの権限。読み取りだけでも Pay-per-use のクレジットが要る |
| ツールが100個以上出て選べない | `X_API_TOOL_ALLOWLIST` を設定して再起動 |
| クラウドの Claude Code から呼ぶと必ず失敗する | 仕様。X 系ドメインが egress で塞がれている。PC の Claude Code を使う |

## 毎晩のパイプラインを実データにする（MCP とは別作業）

`Settings > Secrets and variables > Actions` に **Secret 名だけ**登録:

```
X_BEARER_TOKEN
```

登録すると次の実行から `sample_input` の警告が消えます。消えていなければ:

```bash
python -m src.pipeline opreport
```

で「実データを読めていない」が残っているはずなので、そのまま報告してください。

## 出典

- 公式実装: https://github.com/xdevplatform/xmcp （README を直接読んで書いた）
- ホスト型エンドポイント `https://api.x.com/mcp` の存在は二次情報のみで、
  **公式 README には記載がありませんでした。**（この環境から `docs.x.com` は
  遮断されており確認できていない）。使えるならローカルサーバは不要になりますが、
  その場合も allowlist で書き込みツールを絞れるかは未確認です

---

## 画像・動画を読ませる（`tools/tweet_read.py`）

ツイートの本文は `cdn.syndication.twimg.com`（埋め込み用の公開エンドポイント）
から読めます。**このホストだけは通ります。** ただしメディアは別ホストにあり、
2026-09-01 時点で全滅です。

| ホスト | 用途 | この環境から |
|---|---|---|
| `cdn.syndication.twimg.com` | ツイート本文・投稿者・いいね数 | **通る** |
| `pbs.twimg.com` | 画像 | 403（CONNECT をゲートウェイが拒否） |
| `video.twimg.com` | 動画 | 403 |
| `x.com` | X Articles の本文、通常のページ | 403 |
| `abs.twimg.com` / `ton.twimg.com` / `platform.twitter.com` | その他 | 403 |

**これはコードで回避できません。** egress ポリシーはこのセッションの環境設定で
決まっていて、403 は「組織のポリシーで拒否」という意味です
（`/root/.ccr/README.md`「Do not retry or route around it」）。

### 直し方は2つ

1. **環境のネットワーク設定で上の3ホストを許可する**（`pbs.twimg.com` /
   `video.twimg.com` / `x.com`）。claude.ai/code の環境設定から。
   → https://code.claude.com/docs/en/claude-code-on-the-web
2. **ファイルを直接チャットに添付する。** 設定変更なしで今日から使えます。

### 使い方

```bash
python tools/tweet_read.py https://x.com/user/status/123456789   # URL でも ID でも
python tools/tweet_read.py ./screenshot.png                      # 手元の画像
python tools/tweet_read.py ./demo.mp4 --frames 12                # 動画
```

出力は `data/inbox/<id>/` に落ち、最後に「Read するファイル一覧」が出ます。

**動画はコマに割ってから読みます。** 動画そのものは見られないので、
等間隔の静止画にして1枚ずつ読む形にしてあります（既定8コマ、`--frames` で変更）。
ffmpeg は `pip install imageio-ffmpeg` で入ります。**音声は読めません。**
ナレーションが本体の動画は、その部分が落ちることを承知で使ってください。

`data/inbox/` は `.gitignore` 済み。他人の著作物を public リポジトリに
コミットしないため。
