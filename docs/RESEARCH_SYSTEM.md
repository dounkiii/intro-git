# 探索レイヤ設計 — ちゃっぴー案のレビューと合体版

ChatGPT 案（Grok → Gemini → GPT の3段リサーチ）をレビューし、既存の制作パイプラインと
統合した設計。**採用した部分・変えた部分・その理由**を明示する。

---

## 1. レビュー

### 採用した部分（そのまま or ほぼそのまま）

| 項目 | 評価 |
|---|---|
| **「まだ競合が少ないのに伸び始めている兆候」を狙う** という中核思想 | ここが一番良い。既存パイプラインはニッチ固定だったので、この探索レイヤが欠けていた |
| 100点満点の評価軸（需要20/競合15/収益性20/成長15/コンテンツ化10/アフィリ10/継続5/信頼5） | 配点まで妥当。**そのまま採用**（`src/scout/models.py` の `RUBRIC`） |
| now / watch / drop の3段判定 | 判断が一発で決まるので採用 |
| 「今日の1位」の出力フォーマット | スマホで読む形として良い。**そのまま採用**（`src/scout/report.py`） |
| 上位だけ提示（大量に見せない） | 採用。見なくなったら終わりなので正しい |
| MVP から始めて段階的に足す | 採用 |

### 変えた部分（3点）

#### ① 3社の API を使う理由がない → **2社に減らした**

役割分担は綺麗に見えるが、実際にやっているのは (a) SNS検索 (b) Web検索 (c) 統合評価の3つで、
**(b) と (c) は 1 モデルで両方できる**。3社に分けると、キー・課金・レート制限・SDK差分・
障害点が3倍になる。MVP でこれは自殺行為。

| ちゃっぴー案 | 合体版 | 理由 |
|---|---|---|
| Grok: SNS発掘 | **Grok（維持）+ X API（追加）** | X 上の空気を読む部分は他モデルで代替しにくい。ただし Grok の「伸びている」判断は LLM の主観なので、X API から**いいね/時間を実測**して併用する |
| Gemini: Web調査 | **Claude の `web_search` サーバーツール** | 検索・読解・構造化が1リクエストで完結する。3社目を保守する価値がない |
| GPT: 統合・評価 | **Claude（structured outputs）** | JSON スキーマで出力を固定できるので、パース崩れで承認キューが汚れない |

Grok を残したのは温存ではなく、**X の本文アクセスが本当に代替しにくい**から。
無効化しておけば X API だけで動くし、両方無くてもサンプルで全体が回る。

#### ② スコアが出ることと儲かることは別 → **主観と実測を分離した**

ちゃっぴー案の致命的な弱点。**LLM は「競合の少なさ」を検索せずに推測で答えられてしまう。**
自信満々に「競合が少ないです、15点」と書く。これはただの占いで、意思決定に使えない。

合体版は 2 段構えにした（`src/scout/scoring.py`）。

1. **LLM 採点（主観）** — 評価軸どおりに 100 点満点で採点させる
2. **実測シグナルで補正（客観）**

| 実測 | 補正 |
|---|---|
| 検索で見えた独立ドメインが閾値以上なのに「競合が少ない」と採点 | **-10** ＋ 矛盾フラグ |
| 根拠 URL が 0 件 | **-8** ＋ 矛盾フラグ |
| いいね/時間が閾値未満（X 発掘） | **-5**（「伸び始めている」の否定） |
| いいね/時間が閾値の4倍以上 | **+5** |
| 何度も観測されているのに伸びていない | **-5**（継続性ではなく陳腐化） |
| 過去に実際に収益が出たキーワード | **+5**（成果フィードバック） |

矛盾（`conflicts`）はレポートに `⚠️ LLMと実測の食い違い` として出る。
**LLM を疑える形で人間に渡すこと**が、この設計の主目的。

さらに、順位付けは合計点ではなく **`early_signal = 成長性 × 競合の少なさ`** を主軸にした。
合計点で並べると「すでに大流行しているテーマ」（需要20・成長15・競合1）が上位に来て、
システムの目的と真逆になる。テストで固定してある
（`tests/test_scout_scoring.py::test_順位付けは合計点より早期シグナルを優先する`）。

#### ③ 最大の欠陥: 発掘しても何も作られない → **制作パイプラインに直結した**

ちゃっぴー案は「毎日 TOP3 が出てくる」で終わっている。
**情報収集システムはこれで必ず死ぬ。** 3日で見なくなって終わる。

合体版は `/adopt <id>` を出口に置いた。

```
探索レイヤ  発掘 → 裏取り → 採点 → 日次レポート Issue
                                          │
                        通勤中に  /adopt <id>
                                          ▼
                          data/adopted_niches.yaml
                                          │
制作レイヤ  収集(このクエリで) → 台本/記事 → 承認Issue → /approve → 投稿
                                          ▼
                              収益ログ (data/revenue.csv)
                                          │
                        `/revenue 3200 A8 インボイス`
                                          ▼
                          探索レイヤのスコアに +5 で還る
```

これで **リサーチ → 制作 → 投稿 → 成果 → スコア** が閉じる。
人間の判断は 2 種類だけになる。

- **週1〜数日に1回**: `/adopt` — どのニッチを攻めるか
- **毎日3〜5分**: `/approve` — 出てきた原稿を出すか

### その他の指摘

| 指摘 | 対応 |
|---|---|
| DB / Notion / Sheets は MVP には過剰 | **JSONL + git** にした。履歴と監査ログが無料で付き、Actions のランナーが破棄されても状態が残る |
| Discord / Slack / Telegram 通知 | 不要。GitHub Issue が既に通知面として機能している（アプリのプッシュ通知が来る） |
| 「過去ネタとの比較」を後回しにしている | **MVP に入れた。** 後回しにすると絶対入らないし、同じネタを毎日出すシステムは即座に見捨てられる |
| 重複は「捨てる」ではなく統合すべき | 3日連続で出て**伸びている**ネタは初出より有望。観測回数と伸びを追跡し、伸びなければ減点する形にした |
| 収益化候補に「情報商材」が入っている | 外した。既存 PLAYBOOK で地雷に分類している（ステマ規制・特商法・返金トラブル） |
| YMYL への言及がない | リスク項目に含めるようプロンプトに明記。お金ジャンルは検索評価が厳しい |
| Grok のモデル名 | 変わるので `config.yaml` で指定する形にした。既定値は動かない可能性がある（[docs.x.ai](https://docs.x.ai/) で確認） |

---

## 2. システム構成

```
                    ┌─────────── 探索レイヤ (src/scout/) ───────────┐
                    │                                               │
  X API v2 ────────▶│ sources/x_api.py    いいね/時間を実測          │
  Grok (xAI) ──────▶│ sources/grok.py     X上の兆候（任意・無効可）  │
                    │            │                                  │
                    │            ▼                                  │
                    │ store.py   重複統合＋観測回数の追跡            │
                    │            ▼                                  │
  Claude ──────────▶│ research.py  web_search で裏取り＋実測         │
  (web_search)      │            ▼                                  │
  Claude ──────────▶│ scoring.py   100点採点 → 実測で補正 → 判定     │
  (structured out)  │            ▼                                  │
                    │ report.py   「今日の1位」                      │
                    └──────────────────┬────────────────────────────┘
                                       │ レポート Issue
                            📱 /adopt <id>
                                       ▼
                        data/adopted_niches.yaml
                                       │
                    ┌──────────────────▼── 制作レイヤ (src/) ────────┐
                    │ collectors → processing → monetize → video    │
                    │            → 承認Issue → /approve → 投稿      │
                    └──────────────────┬────────────────────────────┘
                                       ▼
                        data/posts.csv, data/revenue.csv
                                       │ `/revenue`
                                       └──▶ 探索レイヤのスコアへ還元
```

## 3. 必要な API

| API | 必須 | 用途 | 未設定時 |
|---|---|---|---|
| **Anthropic (Claude)** | ◎ | 裏取り（web_search）・採点・台本・記事 | 候補一覧のみ出力、`未採点`と明示 |
| X API v2 | ○ | 需要の兆候収集、いいね/時間の実測 | サンプル候補で動作 |
| xAI (Grok) | △ | X 上の兆候発掘 | スキップ（`scout.grok.enabled: false` が既定） |
| ~~Gemini~~ | ✗ | **不要**（Claude の web_search で代替） | — |
| ~~OpenAI~~ | ✗ | **不要**（Claude で代替） | — |
| TikTok Content Posting | △ | 自動投稿 | `DRY_RUN` でファイル出力のみ |

`ANTHROPIC_API_KEY` 1 つで探索から制作まで通る。

## 4. データ構造

`data/scout/opportunities.jsonl` — 1行1機会。

```jsonc
{
  "id": "f2af5ac317",                    // キーワード集合のハッシュ（翌日も同一判定できる）
  "candidate": {                          // 発掘段階の生ネタ
    "title": "...", "summary": "...", "source": "x_api",
    "keywords": ["インボイス", "会計ソフト"],
    "evidence_urls": ["https://..."],
    "signals": {"likes_per_hour": 52.0}   // 機械計測。総いいね数より重要
  },
  "research": {                           // 裏取り結果
    "why_now": "...", "jp_demand": "...", "overseas_lead": "...",
    "competitor_note": "...", "target_user": "...",
    "monetization_paths": ["アフィリ記事", "有料note"],
    "best_product": "...", "risks": ["..."], "sources": ["https://..."],
    "measured": {"competitor_domains": 3, "evidence_count": 7}   // LLMの自己申告ではない
  },
  "score": {                              // 100点の内訳 + 実測補正
    "demand": 18, "low_competition": 13, "monetizability": 16, "trend_growth": 14,
    "contentability": 8, "affiliate_fit": 8, "durability": 4, "source_reliability": 4,
    "llm_verdict": "now", "scored": true,
    "machine_adjust": -8,
    "adjust_reasons": ["根拠URLが0件で -8"],
    "conflicts": ["LLMは競合が少ないと判断だが独立ドメインが12件"],
    "llm_total": 85, "total": 77, "early_signal": 0.809
  },
  "verdict": "now",                       // LLMと機械判定の保守側
  "action": "比較記事を1本書く",
  "first_seen": "...", "last_seen": "...", "times_seen": 3,
  "status": "adopted"                     // new | adopted | dropped
}
```

`data/adopted_niches.yaml` — 探索と制作の接点。

```yaml
niches:
  - slug: adopted_f2af5ac317        # 制作レイヤのカテゴリ名になる
    label: インボイス2割特例の終了で…
    query: (インボイス OR 2割特例 OR 会計ソフト) lang:ja -is:retweet
    opportunity_id: f2af5ac317
    best_product: 比較記事
    active: true
```

## 5. MVP 実装手順（実施済み）

ちゃっぴー案の MVP 定義（発掘 → 評価 → TOP3 → 保存）に沿ったが、
③の理由で **`/adopt` までを MVP に含めた**（出口が無いと価値が出ないため）。

1. ✅ データモデル（`models.py`）— 評価軸・early_signal・トークン正規化
2. ✅ 発掘元アダプタ（`sources/`）— X API（実測付き）+ Grok（任意）
3. ✅ 裏取り（`research.py`）— Claude web_search + 実測ドメイン数
4. ✅ 採点（`scoring.py`）— 100点採点 + 実測補正 + 保守側判定
5. ✅ 永続化と重複統合（`store.py`）— JSONL、観測回数の追跡
6. ✅ レポート（`report.py`）—「今日の1位」+ 矛盾の明示
7. ✅ ニッチ採用（`niches.py`）— 制作レイヤへの接続
8. ✅ CLI（`python -m src.pipeline scout`）と Actions（`daily-scout.yml`）
9. ✅ テスト 27 件

### 次に足すもの（優先順）

| 優先 | 項目 | 理由 |
|---|---|---|
| 高 | **検索ボリュームの実測** | 現状「競合の少なさ」は検索結果のドメイン数が代理指標。実際の検索需要は測れていない |
| 高 | **採用ニッチ専用のアフィリ案件** | いまは `offers.default` に落ちる。ニッチごとに単価の高い案件を割り当てたい |
| 中 | 既存記事の質の評価 | ドメイン数だけでは「競合が多いが全部薄い」を見分けられない |
| 中 | 採用ニッチの自動休止 | 30日で収益0のニッチは自動で `active: false` にする |
| 低 | Gemini / GPT の追加 | 現状の構成で困ってから。困っていないうちに増やすと保守が破綻する |

## 6. 使い方

```bash
# 探索（サンプル候補、APIキー不要）
python -m src.pipeline scout --sample

# 本番（ANTHROPIC_API_KEY + X_BEARER_TOKEN）
python -m src.pipeline scout --open-issue

# 採用 → 制作へ
python -m src.pipeline command --body "/adopt f2af5ac317"
python -m src.pipeline run --limit 3        # 採用ニッチが自動でクエリに入る

# 成果を戻す（探索レイヤのスコアに +5 で反映される）
python -m src.pipeline revenue --amount 3200 --source A8 --note インボイス
```

## 7. コスト感

`research_limit: 6`（既定）で 1 日あたり Claude API 呼び出しは
**裏取り6回（web_search 付き）+ 採点6回 = 12回**。
制作レイヤの台本・記事生成が別途 1 本あたり 2 回。

`config.yaml` の `scout.research_limit` と `llm.effort` が主なコスト調整点。
API 代を下げたいときは `research_limit` を先に絞る（採点より検索の方が高い）。
