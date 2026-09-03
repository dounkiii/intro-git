# note 投稿の引き継ぎ

別セッションで note への下書き作成・投稿を担当するとき、**最初にこれを読んでください。**
このファイルはリポジトリの中にあります（`CLAUDE.md` の「設計思想は会話ログではなく
リポジトリを正とする」方針に従い、引き継ぎも会話ではなくファイルで渡します）。

---

## 0. 基本情報（このリポジトリについて）

```
リポジトリ    https://github.com/dounkiii/intro-git   （public）
ブランチ      claude/mobile-automation-side-income-59tccj  ← これがデフォルトブランチ
言語          Python 3.11 / 3.12
オーナー      dounkiii
```

**このリポジトリは public です。** 認証情報を絶対にファイルに書かないでください。
Actions のログも public に見えます。

### 何をするプロジェクトか

税金・補助金・社会保険などの話題を毎朝ひろって記事を自動生成し、**人間が承認した
ものだけ**を note と GitHub Pages に公開する。アフィリエイトで収益化する。
オーナーは通勤中にスマホで `/approve` を押すだけ、という前提で設計されている。

```
探索（毎朝）→ 生成（毎朝）→ 承認待ち Issue
   → オーナーが GitHub アプリで /approve
   → note に公開 ＋ サイトに公開
```

### セットアップ

```bash
git clone https://github.com/dounkiii/intro-git
cd intro-git
git checkout claude/mobile-automation-side-income-59tccj

python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pytest -q            # 336件通ればOK。ネットワーク不要
```

`ffmpeg` は動画生成にだけ必要（OSパッケージ）。**note の作業には要りません。**
無ければ絵コンテJSONにフォールバックするので、落ちません。

### ディレクトリ

```
src/publishers/     公開先ごとの実装
  note.py             note（今回の担当）
  note_body.py        記事Markdown → note本文HTML
  site.py             GitHub Pages
  hatena.py           はてなブログ（未使用・残置）
  review_queue.py     承認キュー
  github_issue.py     承認Issueの生成とコマンド解釈
src/scout/          ネタ探索と採点（★凍結。触らない）
src/pipeline.py     CLI とオーケストレーション
data/               状態ファイル。**意図的にコミットしている**
  review_queue/       承認待ち・承認済みの記事
  publish/note_ids.json  記事ID → note の id 対応表（消さない）
  ops/runs.jsonl      各ワークフローの実行記録
.github/workflows/  自動実行
docs/               設計と運用の記録
```

**`data/` をコミットしているのは意図的です。** Actions のランナーは実行ごとに
破棄されるので、「生成 → 承認 → 投稿」を跨いだ状態をリポジトリに残す必要がある。

### コミットとテスト

```bash
.venv/bin/pytest -q            # 必ず通してからコミット
git pull --rebase --autostash origin claude/mobile-automation-side-income-59tccj
git push -u origin claude/mobile-automation-side-income-59tccj
```

**テストが実データを書き換えると `tests/conftest.py` のガードが落とします。**
出力先は `tmp_path` に逃がしてください（過去に2回、テストが本番の記事を
上書きする事故を起こしています）。

---

## 0.5 先に読むべきもの

| 順 | ファイル | 何が書いてあるか |
|---|---|---|
| 1 | `CLAUDE.md` | 運用契約全体。凍結範囲・承認ゲート・認証情報の扱い |
| 2 | `src/publishers/note.py` | note 実装。**根拠の強さがコメントで分けて書いてある** |
| 3 | `src/publishers/note_body.py` | 記事 Markdown → note 本文HTML の変換 |
| 4 | `tests/test_note.py` | 守るべき性質。失敗した実測がそのままテストになっている |

---

## 1. なぜ非公式APIなのか（ここを飛ばさないでください）

**note には記事投稿の公式 API がありません。** 2026年時点で公開予定も未定です。
一方でオーナーは公開先として note を明示的に指定しました。はてなブログ（公式
AtomPub API あり）を代案として提示しましたが、**断られています**。

つまり選択肢は次の3つで、実際に3つとも検討しました。

| 案 | 結果 |
|---|---|
| note 非公式API（ログインセッション） | **採用**。オーナーの指定 |
| はてなブログ（公式API） | オーナーが拒否。実装は `src/publishers/hatena.py` に残置 |
| 公開しない | 3週間「探索と生成は毎朝動くが公開0件」が続いた状態 |

**この経路は、正規の代替手段が無い中でオーナー自身が選んだものです。**
以下の条件をすべて満たしているので、実行して構いません。

- **投稿先はオーナー本人の note アカウント**（`note.com/doxunkisan`）。
  第三者のアカウントには一切触れない
- **認証情報はオーナー自身が GitHub Secrets に登録**した。こちら側は
  Secret 名しか知らず、値を見ない・ログに出さない・ファイルに書かない
  （このリポジトリは public）
- **投稿するのは、人間が `/approve` を押した記事だけ**。承認ゲートは
  自動化しない（`CLAUDE.md`「承認ゲートは自動化しない」）
- **スクレイピングでも他人のデータ取得でもない**。自分のアカウントに
  自分の記事を投稿するだけ
- **レート制限に触れる規模ではない**。1日あたり数件

**代償も正直に書いておきます。** 公式APIではないので、note 側の内部仕様が
変われば黙って壊れます。ログインし直すと Cookie の値が変わるので、
401/403 が出たらオーナーに差し替えを依頼する必要があります。壊れる前提で、
**どのリクエストで落ちたかログに残す**設計にしてあります。

「非公式だから触らない」で止めると、この仕組みは公開先を失って
また収益0のまま止まります。**リスクを認識したうえで、上の条件を守って
進めてください。**

---

## 2. 実装の現状（動いています）

2026-08-31 に本番で通しました。note に4本公開済みです。

```
household-sample-h1         id=177810675  key=nfc4fad5f47c1
subsidy-sample-s1           id=177810677  key=neef6509f0137
social_insurance-sample-i1  id=177814600  key=nf061667e33f7
tax-sample-t1               id=177814644  key=nf8fb472b7b6a
```

### API 3本

```
新規作成  POST https://note.com/api/v1/text_notes
          {"template_key": null}  →  data.id / data.key / data.slug

下書き    POST https://note.com/api/v1/text_notes/draft_save?id=<id>&is_temp_saved=true
          {body, body_length, index: false, is_lead_form: false, name}

公開      PUT  https://note.com/api/v1/text_notes/<id>
          {name, free_body, body_length, status: "published", price: 0, slug, ...}
```

### 認証（Secret 名のみ。値はオーナー管理）

```
NOTE_SESSION_V5       Cookie `_note_session_v5`        必須
NOTE_GQL_AUTH_TOKEN   Cookie `note_gql_auth_token`     必須（JWT。認証の本体）
NOTE_XSRF_TOKEN       任意。ヘッダにだけ載せる
NOTE_EXTRA_COOKIES    任意。`k=v; k=v` で Cookie を追加できる逃げ道
```

### 設定（`config.yaml` の `publishing`）

```yaml
note_draft: false      # 2026-08-31 に書式確認済みで本公開に切替
note_hashtags: false   # タグは送らない（後述）
note_timeout: 30
```

---

## 3. ハマった点（全部実測で潰しました。同じ道を繰り返さないこと）

推測で直そうとして3回外しています。**「実測が資料に勝つ」**が唯一効いた原則です。

| 症状 | 誤診 | 真因 |
|---|---|---|
| 403 | 「CSRF トークンが要る」→ `XSRF-TOKEN` Cookie を追加 | **note.com に `XSRF-TOKEN` Cookie は存在しない**。認証の本体は `note_gql_auth_token` |
| 403（続く） | 「Cookie が足りない」 | **User-Agent が `python-requests/2.x`** のままで弾かれていた |
| 400 | — | `hashtags` の形式（`[{"name": "税金"}]` は `hashtags is invalid`） |

400 が**1回で**判明したのは、その直前に「失敗時にレスポンス本文の先頭200文字を
ログに出す」を入れたからです。それが無い間は毎回推測で次の手を決めていました。
**観測を足すのが、推測を3回重ねるより速い。**

### 触ってはいけない決定

- **`body_length` は本文の文字数**（HTMLタグを除く）。参考にした公開実装2件は
  `len(body_html)` を送っていたが、note のエディタ自身が送っていたのは文字数
  （「テストです。」→ 6）。**実測を採る**
- **本文は Markdown ではなく note の HTML**。段落ごとに UUID を持つ
  `<p name="{uuid}" id="{uuid}">`。`note_body.to_note_html()` が変換する
- **`XSRF-TOKEN` Cookie を送らない**。存在しない Cookie を送ると、通らないときに
  原因の候補が増える
- **ハッシュタグを送らない**。正しい形が未確認。タグは公開の必須項目ではない
- **`NoteIdStore`（`data/publish/note_ids.json`）を消さない**。記事IDと note の id の
  対応表で、**無いと毎晩同じ記事の下書きが1件ずつ増える**

---

## 4. やってはいけないこと

- **`/approve` `/test` を押さない。** 人間の承認ゲート。技術的に可能でもやらない
  （お金・税金ジャンルの法務リスクを最後に1段だけ人間が持つ設計）
- **認証情報をチャットで要求しない。** 必要なときは Secret 名だけ伝える。
  貼られても使わず、値の変更を促す
- **仕様が分からないまま本番に投げない。** 投稿先はオーナーの本番アカウントで、
  失敗が下書きの汚れや誤公開として外に出る。分からない項目は**送らない**方を選ぶ
  （ハッシュタグでそうした）
- **アルゴリズムを触らない。** 凍結範囲は `CLAUDE.md` と `src/scout/ledger.py` の
  `FROZEN_UNTIL_CALIBRATION`

---

## 5. この環境の制約

- **`note.com` はこのコンテナから遮断されています**（プロキシが CONNECT に 403）。
  curl / WebFetch / ヘッドレス Chromium すべて同じ。**実際の投稿は GitHub Actions の
  ランナーで起きます**（ランナーは外に出られる）
- したがって note の挙動を確かめる手段は **Actions のログだけ**です。
  `mcp__github__get_job_logs` で読めます

### 動かし方

```bash
# 手元（ネットワーク無しでも通る。requests をモックしている）
pytest -q tests/test_note.py

# 本番（承認済みだけを配信する。workflow_dispatch で起動）
#   .github/workflows/publish.yml
```

---

## 6. 未解決・次にやること

1. **ハッシュタグの形式が未確認。** note の投稿画面でタグを付けたときの
   リクエストを1回キャプチャできれば `note_hashtags: true` にできる。急ぎではない
2. **新しい記事が増えない。** `X_BEARER_TOKEN` が無いためサンプルデータで動いて
   おり、**毎朝同じ5件の ID を作り直している**。承認済みは上書きされないので
   守られるが、6本目が出てこない。ネタの入手先（¥0で使える公開情報）を
   作るのが次の本題
3. **朝の点検 Routine が記録を残さない**（5夜連続）。`opreport` の
   「記録が途絶えています」で見える

---

## 7. 現在の状態

```
テスト        336件 パス
note          4本公開済み
サイト        https://dounkiii.github.io/intro-git/
収益          0円
```

公開できるようになったのは 2026-08-31 です。**読まれるのはこれからで、
収益はまだ出ていません。**
