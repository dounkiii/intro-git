# スマホ承認型 AI 収益パイプライン

通勤中にスマホだけで回す副業パイプライン。**生産は Claude が全部やり、人間は 1 日 3〜5 分の承認だけ**。

- 実行は GitHub Actions（クラウド）。PC は初期セットアップの 1 回だけ
- 操作面は GitHub モバイルアプリの Issue コメント 1 行（`/approve <id>`）
- 収益は **アフィリエイト・ファースト**。プラットフォーム収益は後乗りのボーナス扱い

📘 **まず読む**: [docs/PLAYBOOK.md](docs/PLAYBOOK.md)（戦略・収益条件の実数・90日プラン・地雷リスト）
📱 **運用手順**: [docs/PHONE_OPS.md](docs/PHONE_OPS.md)（セットアップと毎朝のルーティン）

---

## なぜこの設計なのか（3行）

1. **プラットフォーム収益は入口にならない。** TikTok Creator Rewards は 1万フォロワー＋30日10万再生、
   YouTube Shorts は 90日で 1,000万再生（2027/2/1 から 2,000万）。半年タダ働きになる
2. **閾値ゼロで換金できるのはアフィリエイトと自前商品だけ。** だから動画は集客装置、
   換金は記事とプロフィール導線で行う
3. **完全放置は作れない。** 規約違反・法務リスク・品質崩壊は承認の 1 段でしか止まらないので残す

根拠と出典は [docs/PLAYBOOK.md](docs/PLAYBOOK.md)。

---

## 動作の流れ

```
[毎朝 6:00 JST] GitHub Actions
  X API収集 → スコアリング → 安全性チェック → Claude が台本と記事を生成
    → 縦型ショート動画（TTS + スライド, 1分以上）
    → アフィリCTA・PR表記・免責を強制注入
    → 承認 Issue を作成
                    ↓
[通勤中] スマホで Issue にコメント:  /approve tax-1899234
                    ↓
[即座に] GitHub Actions
  TikTok へ投稿 + 記事を data/articles/ に書き出し + 収益ログに記録
                    ↓
[毎週火曜] 週次レポート Issue（投稿数 / 承認率 / 収益 / 次の打ち手）
```

**ニッチは「お金・税金・社会保険・給付金」**。高単価アフィリが揃い、制度改正でネタが自動供給され、
個人を名指ししないので法務リスクが低い。炎上ネタを使わない理由は PLAYBOOK の 3 に書いた。

---

## ⚠️ 実運用前に必ず読むこと

1. **API 利用規約**
   - X API: 収集は API 経由のみ。スクレイピングは規約違反
   - TikTok Content Posting API: 自動投稿には Developer 申請が必要。
     **未審査アプリは `SELF_ONLY`（本人のみ閲覧可能）でしか投稿できない**
2. **法的リスク**
   - 税務・投資の**断定的な助言はしない**（税理士法・金融商品取引法）。
     「一般的な制度の説明」に留め、出典と免責を必ず付ける（自動付与している）
   - アフィリリンクを含む投稿には **PR 表記が必須**（景品表示法のステマ規制、2023年10月〜）。
     `monetization.disclosure` として自動付与している
3. **安全装置は外さない**
   - `DRY_RUN=true` / `REVIEW_REQUIRED=true` が既定
   - `safety_flags` 付きの案件は `/approve all` の対象外
   - 個人名の名指しは `src/processing/safety.py` が既定でブロックする

---

## セットアップ

詳細は [docs/PHONE_OPS.md](docs/PHONE_OPS.md)。最短ルート:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY だけ入れれば動く
# 動画生成には ffmpeg と日本語フォントが必要
#   Ubuntu: apt install ffmpeg fonts-noto-cjk / macOS: brew install ffmpeg
```

GitHub で回す場合はこれだけ:

1. `Settings > Secrets and variables > Actions` に `ANTHROPIC_API_KEY` を登録
2. `Settings > Actions > General > Workflow permissions` を **Read and write** にする
3. アフィリ審査が通ったら `AFF_*` Secrets を追加（`.env.example` に一覧）

---

## 使い方（ローカル検証）

```bash
# サンプルデータで生成（API キー不要、外部投稿なし）
python -m src.pipeline run --sample --limit 3

# 承認キューの確認
python -m src.pipeline review --list

# Issue コメントのコマンドを手元で試す
python -m src.pipeline command --body "/approve tax-sample-t1"
python -m src.pipeline command --body "/status"

# 承認済みを投稿（DRY_RUN=true の間はファイル出力のみ）
python -m src.pipeline publish --approved

# 収益を記録して週次レポートを見る
python -m src.pipeline revenue --amount 3200 --source A8 --note 確定申告ソフト
python -m src.pipeline report --days 7
```

## Issue コメントコマンド

| コマンド | 動作 |
|---|---|
| `/approve <id>` | 承認 → 次の publish で投稿 |
| `/reject <id> [理由]` | 却下（理由はログに残る） |
| `/approve all` | 未処理を一括承認（**`safety_flags` 付きは除外**） |
| `/status` | キュー状況を返信 |
| `/revenue <金額> <ASP名> [メモ]` | 収益を記録 |

`approval-queue` ラベルの付いた Issue で、リポジトリのオーナー/メンバーのコメントのみ受け付ける。

---

## 環境変数

| 変数 | 説明 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API キー。**これだけで動く**（未設定時はテンプレ生成にフォールバック） |
| `AFF_HUB_URL` 他 `AFF_*` | アフィリリンク。空のスロットを指す案件は自動スキップ |
| `X_BEARER_TOKEN` | X API v2。未設定なら `data/sample_tweets.json` で動く |
| `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API |
| `GITHUB_TOKEN` / `GITHUB_REPOSITORY` | 承認 Issue の作成。Actions 内では自動 |
| `DRY_RUN` | `true`（既定）だと実投稿せずファイル出力のみ |
| `REVIEW_REQUIRED` | `true`（既定）だと承認前は投稿しない |

全項目は `.env.example`。動作パラメータ（ニッチ・CTA・尺・安全設定）は `config.yaml`。

## テスト

```bash
pytest -q
```

## ディレクトリ

```
docs/
  PLAYBOOK.md          戦略・収益条件の実数・90日プラン・地雷リスト
  PHONE_OPS.md         セットアップと通勤中の運用手順
.github/workflows/
  daily-generate.yml   毎朝の生成 → 承認 Issue 作成
  approve-command.yml  /approve コメントで起動 → 投稿
  weekly-report.yml    週次レポート Issue
  tests.yml            pytest
src/
  config.py                設定・環境変数の読み込み
  llm/claude.py            Claude API による台本・記事生成（失敗時はフォールバック）
  collectors/twitter.py    X API から話題を収集
  processing/
    classifier.py          話題度スコアリング
    safety.py              個人攻撃・誤情報リスクのガードレール
    summarizer.py          台本 / アフィリ記事の生成
  monetize/
    affiliate.py           換金経路の解決と CTA・PR表記の注入
    revenue.py             投稿/収益ログと週次レポート
  video/builder.py         TTS + スライド → 縦型 mp4（1分以上に自動調整）
  publishers/
    review_queue.py        承認キュー（状態はリポジトリにコミットされる）
    github_issue.py        承認 Issue の生成とコメントコマンド解釈
    tiktok.py              TikTok Content Posting API
  pipeline.py              全体オーケストレーション（CLI）
  scheduler.py             ローカル用の簡易定期実行
data/
  review_queue/*.json      承認キュー（コミットされる）
  articles/*.md            書き出した記事（コミットされる）
  posts.csv, revenue.csv   ログ（コミットされる）
  output/                  動画・絵コンテ（コミットしない。投稿時に台本から再生成）
```

> GitHub Actions のランナーは実行ごとに破棄されるため、承認キューと記事・ログは
> リポジトリにコミットして状態を引き継ぐ。動画は重いのでコミットせず、投稿時に台本から再生成する。
