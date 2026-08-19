# 通勤中スマホ運用ガイド

毎朝の作業は **3〜5分**。使うアプリは **GitHub モバイルアプリ** だけ。

---

## 毎日のルーティン

```
06:00  GitHub Actions が自動で走る
       収集 → Claude が台本と記事を生成 → 承認 Issue を作成
       ↓
07:30  通知が来る（Issue の作成通知）
       電車でアプリを開く
       ↓
       各案件を上から読む。良ければコメント欄に一行:
           /approve tax-1899234
       ダメなら:
           /reject tax-1899234 個人名が入っている
       ↓
       コメントした瞬間に別の Actions が起動して投稿まで走る
       ↓
       完了リプライが Issue に付く。終わり
```

## コメントコマンド

Issue のコメント欄に打つだけ。1 コメントに複数行書いても全部処理される。

| コマンド | 動作 |
|---|---|
| `/approve <id>` | 承認。次の publish ジョブで投稿される |
| `/reject <id> [理由]` | 却下。投稿されない。理由はログに残る |
| `/approve all` | Issue 内の未処理を全部承認（**フラグ付きは除外される**） |
| `/status` | 現在のキュー状況を返信させる |

`safety_flags` が付いた案件は `/approve all` の対象外。個別に `/approve <id>` する必要がある。
これは意図的な安全装置なので外さないこと。

## 承認カードの読み方

Issue に案件ごとにこういうブロックが並ぶ。

```
### tax-1899234  [スコア 412]
**タイトル**: インボイス登録事業者の消費税、2割特例はいつまで使えるか
**換金経路**: 確定申告ソフト (AFF_ACCOUNTING_SOFT)
**safety_flags**: なし
**尺**: 62秒 / 5スライド
<details><summary>台本を開く</summary> ... </details>
<details><summary>記事下書きを開く</summary> ... </details>
```

見るのは実質 **3 点だけ**:

1. **safety_flags** — 何か付いていたら本文を読む。なければ流し読みで良い
2. **換金経路** — `なし` になっていたら却下（換金できないものは作らない方針）
3. **タイトルが事実として正しいか** — 制度の解釈ミスはここでしか止まらない

---

## セットアップ（PC で 1 回だけ、20〜60分）

### 1. リポジトリを自分のものにする

このリポジトリを自分の GitHub アカウントに置く。GitHub Actions の無料枠を使うので
**Public リポジトリ推奨**（Private だと月 2,000 分の上限がある）。

> Public にする場合、`.env` や生成物をコミットしないこと。`.gitignore` で除外済み。

### 2. Secrets を登録する

`Settings > Secrets and variables > Actions` に入れる。

**最低限これだけで動く:**

| Secret | 説明 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー（[console.anthropic.com](https://console.anthropic.com/)） |

**収益化に必要（アフィリ審査が通ってから）:**

| Secret | 説明 |
|---|---|
| `AFF_HUB_URL` | プロフィールに置くリンク集約ページの URL |
| `AFF_ACCOUNTING_SOFT` | 会計/確定申告ソフトのアフィリリンク |
| `AFF_TAX_ADVISOR` | 税理士紹介のアフィリリンク |
| `AFF_FURUSATO` | ふるさと納税サイトのアフィリリンク |
| `AFF_SECURITIES` | 証券口座のアフィリリンク |
| `AFF_INSURANCE` | 保険相談のアフィリリンク |
| `AFF_PRODUCT_URL` | 自前デジタル商品（note / Tips / BASE）の URL |

**投稿の自動化に必要（後回しで良い）:**

| Secret | 説明 |
|---|---|
| `X_BEARER_TOKEN` | X API v2。未設定ならサンプルデータで動く |
| `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API。**アプリ審査が通るまでは `SELF_ONLY` のみ** |

`GITHUB_TOKEN` は Actions が自動で用意するので登録不要。

### 3. Actions の権限を上げる

`Settings > Actions > General > Workflow permissions` を
**Read and write permissions** にする。Issue を作れるようにするため。

### 4. 動作確認（API キーなしでも通る）

```bash
pip install -r requirements.txt
python -m src.pipeline run --sample --limit 2   # サンプルデータで生成
python -m src.pipeline review --list            # キューを見る
python -m src.pipeline report                   # 収益レポート
```

`DRY_RUN=true`（既定）の間は一切外部投稿しない。

### 5. GitHub モバイルアプリを入れて通知を絞る

アプリを入れ、このリポジトリを Watch する。
通知が多すぎると承認習慣が壊れるので、**Issues だけ**に絞るのがおすすめ。

---

## つまずきポイント

| 症状 | 原因と対処 |
|---|---|
| 承認 Issue が作られない | Workflow permissions が Read only。手順 3 |
| 台本がテンプレのまま（不自然な日本語） | `ANTHROPIC_API_KEY` 未設定。Claude 未使用のフォールバックが出ている |
| `換金経路: なし` ばかり | `AFF_*` Secrets が空。審査が通るまでは `AFF_HUB_URL` だけでも入れる |
| TikTok 投稿が本人にしか見えない | アプリ未審査。`SELF_ONLY` 制限。Developer 申請が必要 |
| `/approve` が無反応 | Issue に `approval-queue` ラベルが付いているか確認（ワークフローの起動条件） |
| 動画が 60 秒未満で Rewards 対象外 | `config.yaml` の `video.min_duration_sec` を 60 以上に |

---

## 運用の終わらせ方

`.github/workflows/daily-generate.yml` の `schedule` をコメントアウトすれば止まる。
生成物とログは `data/` に残るので、再開はいつでもできる。
