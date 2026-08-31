"""動画スクリプトとアフィリエイト記事の生成。

生成は 2 段構え:
  1. `config.yaml` の `llm.provider` で選んだプロバイダ（`src/llm/`）で生成
  2. キーが無い / 失敗した場合はテンプレートベースの決定論的生成にフォールバック

フォールバックを残しているのは、毎朝の cron が API 障害 1 回で止まらないようにするため。
ただしテンプレ出力は日本語として不自然なので、承認カードには `generated_by` が出る。
`generated_by` には実際に生成したプロバイダ名を入れる。プロバイダを変えると文章の
品質分布が変わるので、あとで実績を見るときに Claude 期と Gemini 期を混ぜないため。

収益化ブロック（アフィリ CTA / PR表記 / 免責）は `src/monetize/affiliate.py` が
すべての成果物に強制注入する。換金経路のないコンテンツは作らない方針。
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import Article, Topic, VideoScript
from ..monetize.affiliate import AffiliateEngine, MonetizationBlock

logger = logging.getLogger(__name__)

CATEGORY_LABEL = {
    "tax": "税金ニュース解説",
    "subsidy": "補助金・給付金の話",
    "social_insurance": "年金・社会保険の話",
    "household": "家計とお金の話",
    "enjou": "今話題のニュース",
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "slides": {"type": "array", "items": {"type": "string"}},
        "narration": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
    },
    "required": ["title", "hook", "slides", "narration", "description"],
    "additionalProperties": False,
}

ARTICLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body_markdown": {"type": "string"},
    },
    "required": ["title", "body_markdown"],
    "additionalProperties": False,
}


# 読み上げ速度（文字/秒）。narration の文字数から尺を見積もるのに使う。
#
# **なぜ秒で指示しないのか。** 台本プロンプトには「{min}〜{max}秒に収める」と
# 秒で書いていたが、LLM は自分の書いた文章の読み上げ時間を見積もれない。
# 2026-08-30 の実測では 400字の narration が上限90秒を超え（duration_over）、
# 秒で伝えても効いていないことが分かった。文字数なら数えられる。
#
# 値の根拠は実測1点のみ（400字 → 99秒超、つまり 4.04字/秒 以下）。
# 精度を上げるため builder 側で実測値をログに出している（_fit_duration）。
# ログに 4.0 から離れた値が続いたらここを直す。
SPEECH_CHARS_PER_SEC = 4.0


class Summarizer:
    def __init__(self, config: Config):
        self.config = config
        pub = config.section("publishing")
        self.hashtags: list[str] = pub.get("hashtags", [])
        video = config.section("video")
        self.slide_count = int(video.get("slides_per_video", 6))
        self.min_duration = int(video.get("min_duration_sec", 62))
        self.max_duration = int(video.get("max_duration_sec", 90))
        self.policy: str = config.section("llm").get("editorial_policy", "")
        self.affiliate = AffiliateEngine(config)
        self.llm = config.llm_client()

    # ------------------------------------------------------------------
    def build_script(self, topic: Topic) -> VideoScript:
        """動画スクリプトを生成する。LLM 優先、失敗時テンプレ。"""
        block = self.affiliate.build(topic.category)
        data = self._script_via_claude(topic) if self.llm.available else None
        if data:
            script = self._script_from_data(topic, data, block)
            script.generated_by = self.llm.provider
            return script
        return self._script_from_template(topic, block)

    def build_article(self, topic: Topic, script: VideoScript) -> Article:
        """アフィリエイト記事を生成する。動画より先に換金される主収益源。"""
        block = self.affiliate.build(topic.category)
        data = self._article_via_claude(topic, block) if self.llm.available else None

        if data:
            body = data.get("body_markdown", "")
            title = data.get("title") or script.title
            generated_by = self.llm.provider
        else:
            title, body = self._article_from_template(topic, script)
            generated_by = "template"

        cta = self.affiliate.article_cta_section(block)
        if cta:
            body = f"{body.rstrip()}\n\n{cta}\n"
        if block.liability_note and block.liability_note not in body:
            body = f"{body.rstrip()}\n\n{block.liability_note}\n"

        sources = [t.url for t in topic.tweets if t.url]
        if sources:
            refs = "\n".join(f"- {u}" for u in sources)
            body = f"{body.rstrip()}\n\n## 参考にした投稿\n\n{refs}\n"

        return Article(
            topic_category=topic.category,
            title=title,
            body_markdown=body,
            monetization_route=block.route_summary,
            source_urls=sources,
            generated_by=generated_by,
        )

    # --- Claude ---------------------------------------------------------
    def _system_prompt(self) -> str:
        return (
            "あなたは日本の「お金・税金・社会保険」ジャンルを扱う編集者です。\n"
            "読者は制度に詳しくない会社員・個人事業主です。専門用語は必ず言い換えます。\n"
            "\n【編集方針】\n" + (self.policy or "- 断定を避け、一次情報の確認を促す。")
        )

    def _source_digest(self, topic: Topic) -> str:
        lines = [f"カテゴリ: {topic.category}（{CATEGORY_LABEL.get(topic.category, 'お金の話')}）",
                 f"話題度スコア: {topic.score}", "", "元になった投稿:"]
        for t in topic.tweets:
            lines.append(f"- {t.text.strip()}")
        if topic.safety_flags:
            lines.append("")
            lines.append(f"注意フラグ: {', '.join(topic.safety_flags)}")
        return "\n".join(lines)

    def _char_budget(self) -> tuple[int, int]:
        """narration の合計文字数の下限・上限。

        秒で指示しても LLM は守れないので、読み上げ速度で文字数に換算して渡す。
        """
        return (int(self.min_duration * SPEECH_CHARS_PER_SEC),
                int(self.max_duration * SPEECH_CHARS_PER_SEC))

    def _script_via_claude(self, topic: Topic) -> dict | None:
        prompt = f"""次の話題から、縦型ショート動画の台本を作ってください。

{self._source_digest(topic)}

【要件】
- slides と narration は必ず同じ要素数（{self.slide_count}個）にする
- narration の合計文字数を {self._char_budget()[0]}〜{self._char_budget()[1]}字にする
  （読み上げると {self.min_duration}〜{self.max_duration}秒になる長さ。
    下限: TikTok の収益化対象は1分以上の動画なので短くしない。
    上限: 超えると builder が警告するだけで切り詰められず、尺が伸び続ける）
- hook は冒頭2秒で流し見を止める1文。煽らず、損得か期限を示す
- slides は画面に出す短いテキスト（各30字以内）
- narration は読み上げ文。話し言葉で書く
- description は投稿の説明文（ハッシュタグは含めない。こちらで付与する）
- 元投稿に書かれていない数値や期限を創作しない。曖昧なら「要確認」と書く
- 特定の個人・企業を名指しして批判しない"""
        return self.llm.generate_json(self._system_prompt(), prompt, SCRIPT_SCHEMA)

    def _article_via_claude(self, topic: Topic, block: MonetizationBlock) -> dict | None:
        prompt = f"""次の話題から、ブログ/note 用の解説記事を書いてください。

{self._source_digest(topic)}

【構成（この順番を守る）】
1. 見出しなしの導入2〜3文（誰のどの困りごとの話か）
2. `## 何が変わったのか / 何が論点なのか`
3. `## よくある詰まりどころ`（箇条書き3つ以上。読者が実際につまずく順に）
4. `## どう動けばいいか`（手順として書く）

【要件】
- 1,200〜2,000字程度
- body_markdown は Markdown。h1（#）は使わず h2（##）から始める
- 末尾に CTA セクションは書かない（システム側で付与する）
- 断定的な税務・投資助言をしない。「一般的な制度の説明」に留める
- 元投稿にない数値・期限を創作しない
- 読者が次に何をすべきか1つに絞る"""
        return self.llm.generate_json(self._system_prompt(), prompt, ARTICLE_SCHEMA)

    # --- 組み立て -------------------------------------------------------
    def _script_from_data(self, topic: Topic, data: dict,
                          block: MonetizationBlock) -> VideoScript:
        slides = [s for s in data.get("slides", []) if s]
        narration = [n for n in data.get("narration", []) if n]
        # slides と narration の要素数がずれると動画生成が崩れるので短い方に揃える
        if len(slides) != len(narration):
            n = min(len(slides), len(narration))
            logger.warning("slides(%d) と narration(%d) の数が不一致。%d に揃えます。",
                           len(slides), len(narration), n)
            slides, narration = slides[:n], narration[:n]

        return VideoScript(
            topic_category=topic.category,
            title=data.get("title", topic.headline),
            slides=slides,
            narration=narration,
            description=self._compose_description(data.get("description", ""), topic, block),
            source_urls=[t.url for t in topic.tweets if t.url],
            hook=data.get("hook", ""),
        )

    def _script_from_template(self, topic: Topic,
                              block: MonetizationBlock) -> VideoScript:
        label = CATEGORY_LABEL.get(topic.category, "お金の話")
        body = topic.tweets[0].text.replace("\n", " ").strip()
        hook = f"{label}。知らないと損するかもしれない話です。"

        slides = [label, topic.headline, self._trim(body, 90),
                  "詳細は一次情報をご確認ください", "参考になったらフォローお願いします"]
        narration = [hook, f"{topic.headline}。", self._trim(body, 90),
                     "詳しい要件や期限は、公式発表などの一次情報をご確認ください。",
                     "参考になったらフォローといいねをお願いします。"]

        return VideoScript(
            topic_category=topic.category,
            title=topic.headline,
            slides=slides,
            narration=narration,
            description=self._compose_description(topic.headline, topic, block),
            source_urls=[t.url for t in topic.tweets if t.url],
            hook=hook,
        )

    def _article_from_template(self, topic: Topic,
                               script: VideoScript) -> tuple[str, str]:
        label = CATEGORY_LABEL.get(topic.category, "お金の話")
        body = topic.tweets[0].text.replace("\n", " ").strip()
        markdown = "\n".join([
            f"{label}として話題になっている論点を整理します。",
            "",
            "## 何が論点なのか",
            "",
            body,
            "",
            "## よくある詰まりどころ",
            "",
            "- 自分が対象に含まれるかどうかの判定",
            "- 必要書類と提出期限の確認",
            "- 過去分の取り扱い（遡って適用されるか）",
            "",
            "## どう動けばいいか",
            "",
            "まず一次情報で自分が対象かを確認し、対象なら期限を先に押さえてください。",
        ])
        return script.title, markdown

    def _compose_description(self, base: str, topic: Topic,
                             block: MonetizationBlock) -> str:
        """投稿説明文 = 広告表示 + 本文 + 安全性の注記 + 収益化フッタ + ハッシュタグ。

        広告表示を先頭に置くのは景表法のステマ規制のため。末尾に置くと
        リンクや免責の後ろに埋もれ、「明瞭に分かる」を満たさない恐れがある。
        """
        parts = [self.affiliate.disclosure_header(block), base.strip()]

        if "unverified_claim" in topic.safety_flags:
            parts.append("※未確認の情報を含む可能性があります。")
        if "no_verified_source" in topic.safety_flags:
            parts.append("※出典は認証アカウント以外を含みます。")

        footer = self.affiliate.video_description_footer(block)
        if footer:
            parts.append(footer)
        if self.hashtags:
            parts.append(" ".join(self.hashtags))
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"
