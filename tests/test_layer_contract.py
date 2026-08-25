"""レイヤ境界の契約テスト。

運用開始からの実装バグ12件のうち5件が「探索側と制作側で設定が非対称」だった。
片側は知っているのに反対側は知らない、という形が繰り返し出ている。

これまでの対策は「バグを見つけたら同種を落とすテストを書く」だったが、それは
**バグの形を知ってからしか書けない**（5件すべて事後に書いた）。自動レビューの
指摘を受けて、個別のバグではなく**フィールドの網羅性**を検証する形にした。

  「レイヤ間で渡すデータの全属性を、受け取る側が明示的に処理しているか」

これなら未知の形の非対称も落ちる。新しいフィールドを足した時点で、それを
参照していないレイヤがあればテストが落ちる。
"""
import dataclasses
import inspect
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _code_of(*modules: str) -> str:
    """コメントと docstring を除いたソースを返す。

    説明文に書いた名前を「使っている」と誤判定しないため。ここを分けないと、
    「has_route は使わない」と docstring に書いた瞬間にテストが落ちる。
    """
    import io
    import tokenize

    out: list[str] = []
    for m in modules:
        src = (REPO / "src" / m).read_text(encoding="utf-8")
        prev = None
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            # docstring = 文の先頭に現れる文字列リテラル
            if tok.type == tokenize.STRING and prev in (
                    None, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE,
                    tokenize.NL):
                prev = tok.type
                continue
            out.append(tok.string)
            if tok.type not in (tokenize.NL, tokenize.NEWLINE):
                prev = tok.type
            else:
                prev = tok.type
    return " ".join(out)


# --------------------------------------------------------------------------
# 1. 観測値の網羅性: FunnelMetrics の全フィールドが診断側で使われているか
# --------------------------------------------------------------------------

# 診断に使わないと決めているフィールド。除外理由を必ず書く。
FUNNEL_EXEMPT = {
    "niche": "識別子。判定には使わない",
    "platform": "しきい値の選択に使う（diagnoser_for 側）",
    "attention_minutes": "判断1分あたり収益の集計用。Stage 判定には使わない",
    "api_cost_jpy": "コスト集計用。Stage 判定には使わない",
}


def test_FunnelMetricsの全フィールドが診断側で参照されている():
    """新しい観測値を足したのに診断側が読まないと、#12 と同じ非対称になる。

    #12: スコアリング層は換金経路の実在を知っていたが、診断層は知らなかった。
    結果、提携前の収益0を「案件が悪い」と誤診断していた。
    """
    from src.scout.funnel import FunnelMetrics

    code = _code_of("scout/funnel.py")
    unused = []
    for f in dataclasses.fields(FunnelMetrics):
        if f.name in FUNNEL_EXEMPT:
            continue
        # `m.<name>` の形で参照されていること
        if f". {f.name}" not in code:
            unused.append(f.name)

    assert not unused, (
        f"FunnelMetrics のフィールドが診断側で使われていません: {unused}\n"
        f"使わないと決めたなら FUNNEL_EXEMPT に理由付きで追加してください。")


def test_除外したフィールドには理由が書かれている():
    """理由なしの除外を許すと、除外リストが非対称の隠し場所になる。"""
    for name, reason in FUNNEL_EXEMPT.items():
        assert reason.strip(), f"{name} の除外理由が空です"


def test_除外リストに実在しないフィールドが残っていない():
    """フィールドを消したのに除外だけ残ると、次に同名を足したとき黙って除外される。"""
    from src.scout.funnel import FunnelMetrics

    actual = {f.name for f in dataclasses.fields(FunnelMetrics)}
    stale = set(FUNNEL_EXEMPT) - actual

    assert not stale, f"存在しないフィールドが FUNNEL_EXEMPT に残っています: {stale}"


# --------------------------------------------------------------------------
# 2. 「換金経路がある」の定義がレイヤ間で一致しているか
# --------------------------------------------------------------------------

def test_採点と診断は同じ換金経路の定義を使う():
    """#12 の再発防止。同じ問いに2つの答えがあると、片方だけ直る。

    `has_route`（ハブ・自前商品も含む / CTA を出せるか）と
    `has_direct_offer`（案件のみ / 成約が起こり得るか）は別の問いなので、
    両方あってよい。ただし**採点の observed と診断の direct_route は
    同じものを見なければならない**。ハブを observed に数えると、note の URL を
    登録しただけで全候補が重み 1.0 をもらう。
    """
    code = _code_of("scout/scoring.py")

    # observed 側はハブを含まない has_direct_offer を使う
    assert "has_direct_offer" in code
    # ハブを含む has_route を observed の判定に使っていない
    assert "has_route" not in code


def test_ハブは案件として数えない():
    """ハブはリンク集約ページで、成果報酬の出る案件ではない。"""
    import os

    from src.config import Config
    from src.monetize.affiliate import AffiliateEngine

    before = os.environ.get("AFF_HUB_URL")
    os.environ["AFF_HUB_URL"] = "https://example.com/hub"
    try:
        engine = AffiliateEngine(Config.load())
        # CTA は出せる（has_route は True）
        assert engine.build("tax", quiet=True).has_route
        # だが案件は実在しない
        assert not engine.has_direct_offer()
    finally:
        if before is None:
            os.environ.pop("AFF_HUB_URL", None)
        else:
            os.environ["AFF_HUB_URL"] = before


# --------------------------------------------------------------------------
# 3. 3値フィールドの None を False として扱っていないか
# --------------------------------------------------------------------------

# レビュワーの指摘: 型が合っていても「値の意味」の解釈差は静的解析をすり抜ける。
# None（未記録）と False（実測して無かった）を混同すると、Stage 0 を作った
# 思想（取れていない ≠ 悪い）が崩れる。
TRISTATE_FIELDS = [
    ("src/scout/funnel.py", "direct_route"),
]


@pytest.mark.parametrize("path,field", TRISTATE_FIELDS)
def test_3値フィールドはNoneとFalseを区別している(path, field):
    """`if not m.direct_route` と書くと None と False が同じ扱いになる。

    未記録（None）で「提携していない」と診断すると、観測していない事実を
    観測したことにしてしまう。`is False` / `is None` で明示的に書く。
    """
    code = _code_of(str(pathlib.Path(path).relative_to("src")))

    assert f"not m . {field}" not in code, (
        f"{field} を真偽値として評価しています。None（未記録）と "
        f"False（実測で無かった）が同じ扱いになります。`is False` を使ってください。")
    assert f"{field} is False" in code or f"{field} is None" in code, (
        f"{field} を is False / is None で判定していません。")


def test_direct_routeが未記録なら案件のせいにしない():
    """None（未記録）は判定不能。False（未提携）とも、True とも違う。"""
    from src.scout.funnel import (CAUSE_NOT_MONETIZED, CAUSE_OFFER,
                                  FunnelDiagnoser, FunnelMetrics)

    def cause(direct_route):
        m = FunnelMetrics(niche="n", posts=10, impressions=20000, revenue_jpy=0,
                          engaged=2000, cta_clicks=200, conversions=0,
                          direct_route=direct_route)
        return FunnelDiagnoser().diagnose(m, creatives_tried=2).likely_cause

    # 実測で「案件が無い」→ 案件のせいにしない
    assert cause(False) == CAUSE_NOT_MONETIZED
    # 実測で「案件がある」→ 案件の問題と診断してよい
    assert cause(True) == CAUSE_OFFER
    # 未記録 → False と同じ扱いにしてはいけない（勝手に未提携と決めない）
    assert cause(None) != CAUSE_NOT_MONETIZED


# --------------------------------------------------------------------------
# 4. プロバイダ差の記録がレイヤ間で揃っているか
# --------------------------------------------------------------------------

def test_探索と制作の両方がプロバイダを記録する():
    """#9 の再発防止。Claude 期と Gemini 期を同じデータとして扱わないため。"""
    scout = _code_of("scout/ledger.py")
    factory = _code_of("processing/summarizer.py")

    assert "llm_provider" in scout
    assert "self . llm . provider" in factory


def test_LLMクライアントは同じインターフェースを持つ():
    """アダプタを足したときの取り違えを落とす。"""
    from src.llm.claude import ClaudeClient
    from src.llm.gemini import GeminiClient

    required = ("available", "generate_json", "research")
    for client in (ClaudeClient, GeminiClient):
        for name in required:
            assert hasattr(client, name), f"{client.__name__} に {name} が無い"
        assert client.provider
        assert client.api_key_env
        # research のシグネチャが揃っていること（呼び出し側は1つ）
        assert inspect.signature(client.research).parameters.keys() == \
            inspect.signature(ClaudeClient.research).parameters.keys()


# --------------------------------------------------------------------------
# 5. 保存済みの観測値が古いまま凍結されないか
# --------------------------------------------------------------------------

def test_採用時に換金経路を実測し直す(tmp_path, monkeypatch):
    """探索は新規候補しか採点し直さない（既存は観測回数の更新のみ）ので、
    保存済みの monetization_observed は提携状況が変わっても古いまま残る。
    採用の瞬間に凍結する予測がその古い値だと、「案件が実在した」という事実が
    実際と違う状態で台帳に固定される。"""
    import os

    from src.config import Config
    from src.scout.models import Candidate, Opportunity, Score
    from src.scout.runner import ScoutPipeline

    # 案件は1つも登録されていない（ハブだけ）
    for slot in ("AFF_ACCOUNTING_SOFT", "AFF_TAX_ADVISOR", "AFF_FURUSATO",
                 "AFF_SECURITIES", "AFF_INSURANCE", "AFF_PRODUCT_URL"):
        monkeypatch.delenv(slot, raising=False)
    monkeypatch.setenv("AFF_HUB_URL", "https://example.com/hub")

    pipeline = ScoutPipeline(Config.load())
    monkeypatch.setattr(pipeline.niches, "path", tmp_path / "niches.yaml")
    monkeypatch.setattr(pipeline.ledger, "path", tmp_path / "ledger.jsonl")

    # 「案件が実在した」として保存された古い候補
    stale = Opportunity(
        id="stale01", candidate=Candidate(title="古い候補"), verdict="watch",
        score=Score(scored=True, monetization_observed=True,
                    monetization_inferred=True))
    monkeypatch.setattr(pipeline.store, "get", lambda _id: stale)
    monkeypatch.setattr(pipeline.store, "set_status", lambda *a, **k: None)
    saved: list = []
    monkeypatch.setattr(pipeline.store, "upsert", lambda o: saved.append(o))

    pipeline.adopt("stale01")

    # 実測し直され、ハブしか無いので False になっていること
    assert stale.score.monetization_observed is False
    # 推測側は触らない（observed と inferred は別のもの）
    assert stale.score.monetization_inferred is True
    # 保存もされている（次回以降も古い値が残らない）
    assert saved and saved[0] is stale
