# 税金・お金ショート動画 下書き自動生成パイプライン

**会社員が、初期費用ゼロ・スマホ/PCだけで、税金・お金系のショート動画（YouTube Shorts / TikTok）
を量産する**ための下書き生成パイプラインです。

流れはシンプル:

```
① Claude がその日の税金・お金の話題をリサーチ  →  ② 構造化データ(topics JSON)
                                                          │
                                                          ▼
③ 下書き台本パックを自動生成（フック/台本/テロップ/タイトル案/概要欄/ハッシュタグ/出典/免責）
                                                          │
                                                          ▼
④ 人が最終チェック  →  ⑤ 撮影 or スライド動画化  →  ⑥ 投稿
```

生成物の実例 → [`content/2026-07-28/`](content/2026-07-28/)

## 💰 まず“正直な”お金と現実の話（必読）

夢を壊さない範囲で正直に言います。これは「魔法の自動ATM」ではありません。

- **初期費用ゼロは本当に可能** です。この `drafts` コマンドは有料 API を一切使いません。
  Claude のリサーチ結果（JSON）さえあれば、台本パックが無料で出ます。
- **“完全全自動で寝てても稼ぐ”は非現実的**。少なくとも「顔/声 or スライドで撮る」「最終チェック」
  「投稿」は人が担当します。自動化できるのは一番しんどい**リサーチ＋構成＋台本づくり**の部分。
  ここが1本30〜60分 → 数分になるのが本質的な価値です。
- **収益化は“積み上げ”ゲーム**。YouTube 収益化は登録1,000人＋総再生4,000時間（またはShorts
  1,000万回/90日）等の条件あり。TikTokも同様に条件があります。数本でバズって即収益、はまず無い。
  現実的には「毎日1本×数ヶ月」を淡々と回せるか、が勝負。だからこそ**台本の自動化が効く**。
- **X API / TikTok自動投稿は有料 or 審査必須**。X API Basic は月額課金、TikTok 自動投稿は
  Developer 審査が必要で未審査は下書き(SELF_ONLY)のみ。**初期費用ゼロを守るなら、収集は
  Claude のリサーチ、投稿は手動アップロード**が正解です（下記「運用の2モード」）。

> つまり狙いは「稼げる保証」ではなく、**続けるためのコストを極限まで下げること**。
> 続けられる仕組みがあれば勝率は上がります。

## ⚠️ コンテンツの前提（守ってください）

- **扱うのは税金・お金の“制度・一般解説”のみ**。特定個人を叩く「炎上ネタ」は名誉毀損等の
  リスクがあるため、このプロジェクトでは既定で扱いません。
- **税務・投資は必ず免責を入れる**。生成物には自動で免責文が入りますが、投稿前に一次情報で
  数字をファクトチェックしてください（制度は毎年変わります）。
- **一次情報（公式・報道・専門家）を出典に**。topics JSON に出典URLを必ず入れる設計です。

## 運用の2モード

| モード | 収集 | 投稿 | 費用 | おすすめ |
|--------|------|------|------|----------|
| **A. ゼロ円運用（推奨）** | Claude がリサーチ→`topics/*.json` | 手動アップロード | 0円 | まず始める人 |
| B. API連携（上級） | X API | TikTok API | 月額+審査 | 規模拡大時 |

まずは **モードA** で `drafts` コマンドだけ使えばOKです。

## パイプライン構成

```
[Twitter収集] → [フィルタ/スコアリング] → [安全性チェック] → [スクリプト生成]
      collectors      processing.classifier   processing.safety   processing.summarizer
                                                                          │
                                                                          ▼
                              [TikTok投稿] ← [レビュー承認] ← [動画レンダリング]
                              publishers.tiktok  review_queue    video.builder
```

各ステップは疎結合で、単体で差し替え・テスト可能です。

## セットアップ

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 各種 API キーを設定
# ffmpeg が必要: macOS `brew install ffmpeg` / Ubuntu `apt install ffmpeg`
```

## 使い方（モードA・ゼロ円運用）

```bash
# ① Claude にその日のネタをリサーチしてもらい data/topics/<日付>.json を作る
#    （このリポジトリでは Claude が WebSearch で作成。手動で追記・修正もOK）

# ② 下書き台本パックを生成（★これが中核。API不要・無料）
python -m src.pipeline drafts --topics data/topics/2026-07-28.json
#   → content/2026-07-28/ に各ネタの .md（下書き）と .storyboard.json が出力される

# ③ content/<日付>/*.md を開いて最終チェック → 撮影 or スライド動画化 → 投稿
```

`topics JSON` の書き方は [`data/topics/2026-07-28.json`](data/topics/2026-07-28.json) を
テンプレートにしてください（`id / category / title / hook / key_points / takeaway /
sources / disclaimers`）。

### （任意）スライドから動画まで自動化したい場合

```bash
# storyboard.json から縦型mp4を生成（要 ffmpeg。無ければ絵コンテJSONにフォールバック）
python -m src.pipeline run --sample     # サンプルデータでパイプライン全体を試す
```

## 使い方（モードB・API連携／上級）

```bash
python -m src.pipeline run --limit 10         # X API 収集〜動画生成〜レビュー投入
python -m src.pipeline review --list          # レビューキューの確認
python -m src.pipeline publish --approved     # 承認済みを TikTok へ投稿(DRY_RUN=falseで実投稿)
python -m src.scheduler --interval 3600       # 定期実行（cron相当）
```

## 環境変数（`.env`）

| 変数 | 説明 |
|------|------|
| `X_BEARER_TOKEN` | X API v2 Bearer Token |
| `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API のアクセストークン |
| `OPENAI_API_KEY` | （任意）スクリプト要約に LLM を使う場合 |
| `DRY_RUN` | `true`（既定）だと実投稿せずファイル出力のみ |
| `REVIEW_REQUIRED` | `true`（既定）だと承認前は投稿しない |

## テスト

```bash
pytest -q
```

## ディレクトリ

```
data/
  topics/<日付>.json   その日の税金・お金の話題（Claudeがリサーチ→構造化）
content/<日付>/         生成された下書きパック（.md）と storyboard(.json)
src/
  drafts/generator.py  ★ topics JSON → 下書き台本パック（モードAの中核・API不要）
  config.py            設定・環境変数の読み込み
  collectors/twitter.py  （モードB）X API からトピックを収集
  processing/
    classifier.py      トピック分類・話題度スコアリング
    safety.py          個人攻撃・誤情報リスクのガードレール
    summarizer.py      動画ナレーション用スクリプト生成
  video/builder.py     TTS + スライド → 縦型 mp4
  publishers/
    review_queue.py    人間レビュー用キュー
    tiktok.py          （モードB）TikTok Content Posting API
  pipeline.py          全体オーケストレーション（CLI: drafts/run/review/publish）
  scheduler.py         定期実行
```

## 毎日の回し方（テンプレ）

1. 朝、Claude に「今日の税金・お金の話題を3つリサーチして topics JSON にして」と依頼
2. `python -m src.pipeline drafts --topics data/topics/<今日>.json`
3. `content/<今日>/` の下書きを1本選び、スマホで撮る or スライドにして声を入れる
4. 投稿。概要欄・ハッシュタグはコピペするだけ

「毎日1本を無理なく」を回すための道具です。
