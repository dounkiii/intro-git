# このリポジトリで作業する前に読むこと

**このプロジェクトの設計は凍結されています。** アルゴリズムを変更してよい条件は
3つだけで、それ以外の理由（「もっと良い設計を思いついた」を含む）では変更しません。

セッションが切り替わっても運用ルールが維持されるよう、**設計思想は会話ログではなく
このリポジトリを正（Single Source of Truth）とします。**

---

## 最初に読むファイル（この順番で）

| 順 | ファイル | 内容 |
|---|---|---|
| 1 | **`docs/OPERATIONS.md`** | **運用契約。再開条件と変更禁止範囲。迷ったらここ** |
| 2 | `docs/RESEARCH_SYSTEM.md` | 設計判断の全記録（6ラウンド）。「なぜそうなっているか」 |
| 3 | `docs/PLAYBOOK.md` | 収益戦略・プラットフォーム条件の実数・法務上の地雷 |
| 4 | `docs/PHONE_OPS.md` | セットアップとオーナーの日次手順 |
| 5 | `data/scout/ledger.jsonl` | 予測・実績・レビュー履歴。数字は全部ここ |
| 6 | `docs/REVIEW_REQUEST.md` | ChatGPT へのレビュー依頼窓口。**常に最新の依頼だけを置く** |

---

## アルゴリズムを変更してよい3条件

1. **初売上が出た** — ただし配点は変えず、まず `first_revenue_postmortem()` で
   事実を記録して再現性を確認する
2. **Test / Adopt 合計20件で売上0** — `python -m src.pipeline calibrate` で
   予測 vs 実績を見てから
3. **5件レビューで同じ運用異常が2回連続** — 点検対象は**実装バグ・運用障害のみ**

上記以外では変更しません。特に「もっと良いアルゴリズムを思いついた」は再開条件ではありません。

## 20件未満でも直してよいもの（実装バグ・運用障害）

- 明確な実装バグ
- 採用しても公開されない（`publish_zero` / `publish_low`）
- metrics が取れない（`metrics_missing`）
- 状態遷移がおかしい（`transition_stuck`）
- **人間の明示指示が無視される**（`/adopt` が OBSERVE に落ちる等）

コード上の定数: `src/scout/ledger.py` の `FIXABLE_BEFORE_CALIBRATION`

## 20件未満では触らないもの（アルゴリズム）

100点の配点 / observed→点数の mapping / `scale_gate`（CV2件・売上2回） /
speculative しきい値（機会30・確信0.45） / `opportunity` の計算式（√(D×B)） /
monetization の重み（1.0/0.6/0.2） / percentile 化 / 回帰 / 機械学習

コード上の定数: `src/scout/ledger.py` の `FROZEN_UNTIL_CALIBRATION`

---

## 崩してはいけない設計判断（過去に潰したバグ）

実装を触るとき、この4つを再導入しないこと。**どれもテストでは検出できない種類**で、
「コードとして正しく動くが目的と逆に働く」バグでした。

| 判断 | 崩すと起きること | 該当テスト |
|---|---|---|
| **confidence を順位スコアに掛けない** | 早いトレンドほど根拠が薄いので、掛けると成熟したネタばかり上位に来る | `test_confidenceは順位スコアに掛けない` |
| **Stage 1 は症状。原因を断定しない** | 制作が悪いだけの良いニッチを捨てる。ニッチ撤退には比較材料が必要 | `test_配信されないだけではニッチ撤退にしない` |
| **高機会×低確信は CHEAP_TEST で試す** | 一番発見したい候補が watch で放置される | `test_確信が低くても機会が高ければ小さく試す` |
| **1件の売上で SCALE しない** | 偶然の成功に制作能力を4倍投入する | `test_初回売上ではSCALEにしない` |

加えて:

- **レイヤ境界の契約は `tests/test_layer_contract.py` が守る。** 非対称バグ
  （片側は知っているのに反対側は知らない）が12件中5件だったため、個別のバグを
  追うのをやめ、**フィールドの網羅性**を検証している。`FunnelMetrics` に
  観測値を足したら診断側でも読むこと。読まないなら `FUNNEL_EXEMPT` に理由を書く
- **`observed` は「案件が実在した」だけを意味する。** ハブ（`AFF_HUB_URL`）を
  数えない。数えると note の URL を登録しただけで全候補が重み 1.0 をもらい、
  相乗平均で「金になるか」を効かせる設計が無効になる
- **3値（None / False / True）の None を False と混同しない。** `is False` と
  書く。`not x` と書くと「未記録」が「実測して無かった」になる
- **観測は推測を置き換える**（足し引きしない）。`src/scout/evidence.py`
- **「取れていない」を「悪い」と読み替えない**。データ欠損は Stage 0（判定不能）
- **換金経路のないコンテンツは作らない**。ただし `AFF_*` が無いことを
  「金にならない」とは学習させない（observed / inferred を分離）

## 認証情報はチャットに要求しない

**ログインID・パスワード・銀行情報・API シークレットそのものをオーナーに
要求しない。** 貼られても使わず、変更を促す。

Secrets が必要なときは **値ではなく Secret 名だけ**を指示する
（例:「`AFF_ACCOUNTING_SOFT` を登録してください」）。こちらが必要なのは
プログラム名・審査状況・広告リンクURL・Secret 名までで、認証情報は
オーナー側だけで管理する。A8.net は成果報酬の振込先口座に紐づくため、
漏れると金銭被害に直結する。

このリポジトリは public。認証情報をファイルに書かない。

## 承認ゲートは自動化しない

`/approve` と `/test` は人間が押します。これは未完成だからではなく、
**お金・税金ジャンルの法務リスク（税理士法・景表法・名誉毀損・誤情報）を
最後に1段だけ人間が持つための安全設計**です。技術的に自動化できても、しません。

`DRY_RUN=true` / `REVIEW_REQUIRED=true` が既定であること、
`safety_flags` 付きが `/approve all` の対象外であることも同様に維持します。

---

## 役割分担

| 担当 | 内容 |
|---|---|
| **Claude Code** | コード作成・修正、テスト、コミット、レポート読解、実データ診断、改善実装 |
| **オーナー（人間）** | Secrets 登録、アカウント作成と ASP 審査、`/test` `/approve`、実績入力（週1回30秒） |
| **ChatGPT** | 設計レビュー、診断のセカンドオピニオン、改善案の妥当性確認 |

やり取りは「Claude Code の結果 → ChatGPT レビュー → 実装」のループで回ります。

**依頼は `docs/REVIEW_REQUEST.md` を上書きして渡す。** オーナーが送るのは
このファイルの URL 1行だけで固定になる（リポジトリは public）。長文を毎回
コピペさせない。ファイルは初見でも読めるように前提から書く。

  https://github.com/dounkiii/intro-git/blob/claude/mobile-automation-side-income-59tccj/docs/REVIEW_REQUEST.md

**レビューは自動で回る。** `docs/REVIEW_REQUEST.md` を push すると
`design-review.yml` が LLM に投げ、指摘を `design-review` ラベルの Issue に
コメントする。Claude Code はそれを読んで実装する。オーナーの作業は0。

  python -m src.pipeline critique --issue <番号>    # 手元で回すとき

レビュワーは迎合しやすいので、スキーマ側で具体性を強制している
（`breaks_when` 必須 / 凍結対象への提案は `frozen_violation` へ分離 /
blocker・should_fix が0件の回は明記する）。**同意しかない回が続くなら、
レビュー自体の費用対効果を見直す。**

ChatGPT に人力で見せたいときだけ、`docs/REVIEW_REQUEST.md` の URL を渡す
（リポジトリは public）。長文をコピペさせない。

---

## LLM プロバイダ

既定は **Gemini（無料枠）**。`config.yaml` の `llm.provider` で `claude` に切替可。
差し替えは凍結対象ではありません（アルゴリズムではなくアダプタ）。理由と経緯は
`docs/RESEARCH_SYSTEM.md` の第7ラウンド。

- 必要な環境変数: `GEMINI_API_KEY`（https://aistudio.google.com/apikey・カード不要）
- 無料枠の上限に当たったら `config.yaml` の `scout.research_limit` を下げる
- プロバイダは予測行（`llm_provider` / `llm_model`）に記録される。
  **Claude 期と Gemini 期の予測を同じデータとして校正しないこと**

## 毎朝の自動点検

`data/ops/runs.jsonl` に**ワークフロー自身が実行結果を書いて push する**
（失敗した回も `if: always()` で記録される）。毎朝 21:40 UTC = 06:40 JST に
Routine が新しいセッションを起動し、次を見る。

```bash
python -m src.pipeline opreport      # 要確認の回だけを出す
```

**この経路にした理由。** `api.github.com` はこの環境のプロキシで止まり
（"GitHub access is not enabled for this session"）、Routine から起動される
セッションには GitHub MCP ツールも渡らない。**git だけが通る**ため、
Actions のログに頼らずリポジトリの中に記録を残す必要がある。

異常マーカー（`src/ops/runlog.py` の `MARKERS`）は**実際に起きたバグから採る**。
推測で増やすと誤検知で狼少年になる。**status が success でも中身は壊れうる**
（バグ12件のうち失敗として通知されたのは1件だけ。残りは success のログから見つけた）。

## 開発コマンド

```bash
pytest -q                                  # テスト（現在221件）
python -m src.pipeline scout --sample      # 探索（APIキー不要）
python -m src.pipeline run --sample        # 制作
python -m src.pipeline report --days 7     # 週次レポート + 台帳
python -m src.pipeline calibrate           # 予測 vs 実績（20件以降）
python -m src.pipeline remind --days 7     # 未更新ニッチのリマインド
python -m src.pipeline opreport            # 要確認だったスケジュール実行
python -m src.pipeline critique --issue N  # 設計レビューを回す
```

コードを変更したら必ず `pytest -q` を通してからコミットします。

---

## 再開条件が発火したときの出力形式

診断は **`docs/OPERATIONS.md` §9 の5節形式**で書きます（事実 / 診断 / Ledger上の根拠 /
整合性チェック / 判定）。**変更案は5節の判定が出てから。**
事実と解釈を混ぜた診断は、凍結済みのアルゴリズムを触る口実になりやすいためです。
