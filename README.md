# Twitter → TikTok 自動化パイプライン

Twitter(X) から「炎上」「税金問題」に関する話題を収集し、要約スクリプトを生成、
TTS(音声合成) + スライドで縦型ショート動画を作り、TikTok へ投稿するための
モジュラーなパイプラインです。**Threads（テキスト投稿）への出力**にも対応しています。

> Threads で稼ぐための運用戦略（AI で自動化する具体策・90日ロードマップ・収益導線）は
> [`docs/threads-monetization-strategy.md`](docs/threads-monetization-strategy.md) を参照してください。

## ⚠️ 重要な前提（必ず読んでください）

このプロジェクトは技術的な土台（スキャフォールド）です。実運用の前に以下を理解してください。

1. **API 利用規約の遵守**
   - X (Twitter) API: 自動収集は API 経由で行う必要があり、プラン（Free/Basic/Pro）ごとに
     取得上限があります。スクレイピングは規約違反になり得ます。
   - TikTok Content Posting API: 自動投稿にはアプリ審査（Developer 申請）が必要で、
     未審査アプリは `SELF_ONLY`（本人のみ閲覧可能な下書き）でしか投稿できません。
2. **法的リスク（炎上ネタの扱い）**
   - 「炎上」は特定の個人・企業を対象にしがちで、**名誉毀損・侮辱・プライバシー侵害**の
     リスクがあります。事実確認のない情報の拡散は法的責任を負う可能性があります。
   - 本パイプラインは **既定で人間のレビュー承認（review queue）を必須** とし、
     `DRY_RUN=true` で動きます。無審査の全自動投稿は推奨しません。
3. **プラットフォームのポリシー**
   - TikTok/X ともに、嫌がらせ・誤情報・なりすましを禁止しています。
     収集元は一次情報（本人アカウント・公式発表・報道機関）を優先してください。

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

## 使い方

```bash
# 収集〜動画生成まで（投稿はせずレビューキューに積む）
python -m src.pipeline run --limit 10

# レビューキューの確認
python -m src.pipeline review --list

# 承認済みアイテムを TikTok へ投稿（DRY_RUN=false のとき実投稿）
python -m src.pipeline publish --approved

# Threads（テキスト）へ投稿する場合は --target threads
python -m src.pipeline publish --approved --target threads

# 定期実行（cron 相当）
python -m src.scheduler --interval 3600
```

## 環境変数（`.env`）

| 変数 | 説明 |
|------|------|
| `X_BEARER_TOKEN` | X API v2 Bearer Token |
| `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API のアクセストークン |
| `THREADS_ACCESS_TOKEN` | Threads API (Meta Graph API) のアクセストークン |
| `THREADS_USER_ID` | 投稿先の Threads ユーザー ID |
| `OPENAI_API_KEY` | （任意）スクリプト要約に LLM を使う場合 |
| `DRY_RUN` | `true`（既定）だと実投稿せずファイル出力のみ |
| `REVIEW_REQUIRED` | `true`（既定）だと承認前は投稿しない |

## テスト

```bash
pytest -q
```

## ディレクトリ

```
src/
  config.py            設定・環境変数の読み込み
  collectors/twitter.py  X API から炎上/税金トピックを収集
  processing/
    classifier.py      トピック分類・話題度スコアリング
    safety.py          個人攻撃・誤情報リスクのガードレール
    summarizer.py      動画ナレーション用スクリプト生成
  video/builder.py     TTS + スライド → 縦型 mp4
  publishers/
    review_queue.py    人間レビュー用キュー
    tiktok.py          TikTok Content Posting API
    threads.py         Threads API（テキスト投稿）
  pipeline.py          全体オーケストレーション（CLI）
  scheduler.py         定期実行
```
