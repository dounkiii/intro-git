# スマホ承認型 AI 収益パイプライン

通勤中にスマホだけで回す副業パイプライン。**生産は Claude が全部やり、人間は 1 日 3〜5 分の承認だけ**。

- 実行は GitHub Actions（クラウド）。PC は初期セットアップの 1 回だけ
- 操作面は GitHub モバイルアプリの Issue コメント 1 行（`/adopt` と `/approve`）
- 収益は **アフィリエイト・ファースト**。プラットフォーム収益は後乗りのボーナス扱い

**2 層構成**

| レイヤ | やること | 人間の判断 | 頻度 |
|---|---|---|---|
| **探索** (`src/scout/`) | まだ競合が薄いのに伸び始めたネタを発掘・裏取り・採点 | `/test <id>` 小さく試す ／ `/adopt <id>` 通常運用 | 週1〜数日に1回 |
| **制作** (`src/`) | 採用ニッチで台本・記事・動画を生成し投稿 | `/approve <id>` 出すか出さないか | 毎日3〜5分 |
| **検証** (`src/scout/ledger.py`) | 予測を凍結し、実績と突き合わせて配点を校正 | `/m <niche> <views> <revenue>` | 週1回30秒 |

⚙️ **運用の契約**: [docs/OPERATIONS.md](docs/OPERATIONS.md)（**設計は凍結済み**。
アルゴリズムを触ってよい3条件と、触ってはいけないものの線引き）
📘 **戦略**: [docs/PLAYBOOK.md](docs/PLAYBOOK.md)（収益条件の実数・90日プラン・地雷リスト）
🔎 **探索レイヤ設計**: [docs/RESEARCH_SYSTEM.md](docs/RESEARCH_SYSTEM.md)（評価軸・実測補正・データ構造）
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
[毎朝 5:00 JST] GitHub Actions — 探索
  X API / Grok で兆候発掘 → 過去ネタと統合 → Claude(web_search) で裏取り
    → 100点採点。測れた軸は実測が推測を置き換える（SERP分類・いいね/時間・根拠数）
    → 機会スコア √(発見 × 収益) 順に並べて「今日の1位」Issue
                    ↓
[通勤中] スマホで:  /test f2af5ac317      ← 確信が低いネタは「小さく試す」
                    /adopt f2af5ac317     ← 確信があるなら通常運用
                    ↓
        data/adopted_niches.yaml に登録され、制作レイヤのクエリになる
                    ↓
[毎朝 6:00 JST] GitHub Actions — 制作
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
[週1回] スマホで:  /m adopted_xxx 6000 3200      ← 累計views と累計revenue だけ
                    ↓
        投稿数は自動入力。増分は自動計算。1数字だけでも可（/m xxx 3200）
        入れなくても Stage 0（判定不能）として記録され、運用は止まらない
                    ↓
        ファネル段階を診断（Stage0 判定不能 / 1 配信の失敗 〜 5 売れている）
        Stage は症状、原因は別に推定（creative / niche / funnel / offer）
        ニッチ撤退は「2種類以上の切り口で配信されない」まで提案しない
                    ↓
        実績から投資レベルが自動遷移（CHEAP_TEST → ADOPT → SCALE / EXIT）
                    ↓
[毎週火曜] 週次レポート Issue
        投稿数 / 承認率 / 収益 / **判断1分あたり収益** / 詰まっている段階
                    ↓
        予測 vs 実績を Experiment Ledger に蓄積 → 20件で配点を校正
```

**スコアの構造**

```
opportunity = √(discovery × business)     ← 最終順位（相乗平均）
confidence  = 0〜1                        ← 順位には掛けず、別に表示する

discovery = 成長性 × 競合の空き            「今入り込む余地があるか」
business  = 需要 × 収益化 × 制作相性       「入って金になるか」
```

片方がゼロに近い候補は上位に来ない。「伸びているが金にならない」も
「金になるが大手だらけ」も除外される。

**確信度はスコアに掛けない。** 本当に早いトレンドほど根拠が薄いので、掛けると
成熟したネタばかり上位に来てしまう。確信度は「やる/やらない」ではなく
**いくら賭けるか**を決める。

| 投資レベル | 1回の生成 | 公開上限 | 遷移条件 |
|---|---|---|---|
| `CHEAP_TEST` | 1本 | 3本 | 確信が低いが機会が高い候補はここから |
| `ADOPT` | 2本 | 上限なし | 初回売上が出たら昇格 |
| `SCALE` | 4本 | 上限なし | **再現性を確認したら**（CV 2件 or 売上2回）昇格 |
| `EXIT` | 0 | — | 2種類以上の切り口で配信されなければ |

昇格には歯止めが2つある。**1件の売上では SCALE にしない**（初回の成功シグナルへの
過剰反応を防ぐ）。**Stage 2〜4 で原因が未解消のあいだは生成枠を増やさない**
（悪い導線に対して制作量だけ増やさない）。

詳細は [docs/RESEARCH_SYSTEM.md](docs/RESEARCH_SYSTEM.md)。

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
# 探索: サンプル候補で「今日の1位」を出す（API キー不要）
python -m src.pipeline scout --sample

# 採用して制作対象にする
python -m src.pipeline command --body "/adopt f2af5ac317"

# サンプルデータで生成（API キー不要、外部投稿なし）
python -m src.pipeline run --sample --limit 3

# 承認キューの確認
python -m src.pipeline review --list

# Issue コメントのコマンドを手元で試す
python -m src.pipeline command --body "/approve tax-sample-t1"
python -m src.pipeline command --body "/status"

# 承認済みを投稿（DRY_RUN=true の間はファイル出力のみ）
python -m src.pipeline publish --approved

# 実績を入れてファネル段階を診断（累計views と累計revenue だけでよい）
python -m src.pipeline command --body "/m adopted_xxx 6000 3200"

# 未更新の採用ニッチをリマインド
python -m src.pipeline remind --days 7

# 収益を記録して週次レポート（Experiment Ledger のサマリ付き）を見る
python -m src.pipeline revenue --amount 3200 --source A8 --note 確定申告ソフト
python -m src.pipeline report --days 7

# 予測 vs 実績の対応表（配点の見直しはこれを見てから）
python -m src.pipeline calibrate
```

## Issue コメントコマンド

| コマンド | 動作 |
|---|---|
| `/approve <id>` | 承認 → 次の publish で投稿 |
| `/reject <id> [理由]` | 却下（理由はログに残る） |
| `/approve all` | 未処理を一括承認（**`safety_flags` 付きは除外**） |
| `/status` | キュー状況を返信 |
| `/revenue <金額> <ASP名> [メモ]` | 収益を記録 |
| `/adopt <id>` | 採用 → 翌朝から制作対象。確信度から投資レベルを自動判定。**予測が凍結される** |
| `/test <id>` | **小さく試す**（CHEAP_TEST）。1回1本・公開3本まで。配信が成立すれば自動で通常運用へ |
| `/scale <id>` | 生成枠を増やす（SCALE） |
| `/drop <id>` | そのネタを捨てる（以後再提示されない） |
| `/m <niche> <累計views> <累計revenue>` | 実績を記録してファネル段階を診断（`/metrics` も同じ）。投稿数は自動、1数字だけでも可 |

`approval-queue` / `scout-report` ラベルの付いた Issue で、
リポジトリのオーナー/メンバーのコメントのみ受け付ける。

---

## 環境変数

| 変数 | 説明 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API キー。**これだけで動く**（未設定時はテンプレ生成にフォールバック） |
| `AFF_HUB_URL` 他 `AFF_*` | アフィリリンク。空のスロットを指す案件は自動スキップ |
| `X_BEARER_TOKEN` | X API v2。収集と兆候発掘。未設定ならサンプルで動く |
| `XAI_API_KEY` | Grok (xAI) 発掘。任意（`scout.grok.enabled: true` で有効化） |
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
  OPERATIONS.md        運用フェーズの契約（再開条件と変更禁止範囲）
  PLAYBOOK.md          戦略・収益条件の実数・90日プラン・地雷リスト
  RESEARCH_SYSTEM.md   探索レイヤ設計（評価軸・実測補正・データ構造）
  PHONE_OPS.md         セットアップと通勤中の運用手順
.github/workflows/
  daily-scout.yml      毎朝の探索 → リサーチ結果 Issue 作成
  daily-generate.yml   毎朝の生成 → 承認 Issue 作成
  weekly-metrics.yml   週1回、実績が未更新の採用ニッチをリマインド
  approve-command.yml  /approve コメントで起動 → 投稿
  weekly-report.yml    週次レポート Issue
  tests.yml            pytest
src/
  config.py                設定・環境変数の読み込み
  llm/claude.py            Claude API（生成 / web_search 調査）。失敗時はフォールバック
  scout/                   === 探索レイヤ ===
    sources/x_api.py       X API から需要の兆候 + いいね/時間の実測
    sources/grok.py        Grok (xAI) 発掘。任意・無効可
    research.py            web_search で裏取り（URL とタイトルを実測値として保持）
    evidence.py            観測と推測の分離。実測は推測を置き換える
    serp.py                SERPの守備力。provider差し替え式（既定は無料の代理指標）
    scoring.py             100点採点 → 実測で置換 → 保守側判定 → 機会スコア順
    explore.py             explore/exploit 予算 + 探索候補の相対選定
    commitment.py          投資レベル（小さく試す→通常→増やす→撤退）と生成枠
    funnel.py              Stage0〜5 の切り分け、原因推定、試行回数ベースの撤退判定
    ledger.py              予測の凍結・実績追記・判断時間の積算・校正ゲート
    store.py               JSONL 永続化と重複統合（観測回数の追跡）
    niches.py              /adopt で制作レイヤへ接続
    report.py              「今日の1位」レポート
    runner.py              探索パイプライン
  === 制作レイヤ ===
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
  scout/opportunities.jsonl 探索結果（コミットされる）
  scout/ledger.jsonl       予測 / 実績 / 判断時間の台帳（コミットされる）
  adopted_niches.yaml      採用ニッチ = 探索と制作の接点（コミットされる）
  review_queue/*.json      承認キュー（コミットされる）
  articles/*.md            書き出した記事（コミットされる）
  posts.csv, revenue.csv   ログ（コミットされる）
  output/                  動画・絵コンテ（コミットしない。投稿時に台本から再生成）
```

> GitHub Actions のランナーは実行ごとに破棄されるため、承認キューと記事・ログは
> リポジトリにコミットして状態を引き継ぐ。動画は重いのでコミットせず、投稿時に台本から再生成する。
