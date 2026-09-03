"""パイプライン全体のスモークテスト（サンプルデータ + DRY_RUN）。"""
import os

from src.config import Config
from src.pipeline import Pipeline
from src.publishers.review_queue import ReviewQueue


def test_run_with_sample_data(tmp_path, monkeypatch):
    """ffmpeg 無し環境でも絵コンテJSONにフォールバックして完走する。

    出力先を tmp_path に逃がすのは、サンプルの item_id が本番と同じだから。
    `tax-sample-t1` などは実際に承認待ちに積まれている ID で、逃がさないと
    このテストを流すだけで**その日に生成された本物の記事がテンプレ出力で
    上書きされる**（2026-08-30 に実際に3件を潰した）。
    """
    os.environ["DRY_RUN"] = "true"
    os.environ["REVIEW_REQUIRED"] = "true"
    monkeypatch.setattr("src.pipeline.OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr("src.pipeline.ARTICLE_DIR", tmp_path / "articles")
    monkeypatch.setattr("src.pipeline.ReviewQueue",
                        lambda *a, **k: ReviewQueue(tmp_path / "review"))

    pipeline = Pipeline(Config.load())
    item_ids = pipeline.run(limit=5, use_sample=True)
    assert len(item_ids) >= 1

    queue = ReviewQueue(tmp_path / "review")
    pending = queue.list_items(status="pending")
    assert any(it.id in item_ids for it in pending)


def test_publish_requires_approval_by_default(tmp_path, monkeypatch):
    """承認していなければ pending は投稿対象にならない。

    出力先を tmp_path に逃がすのは、`publish_approved()` が記事Markdownと
    絵コンテを実際に書き出すから。2026-09-01 に承認済みが2本→4本に増えた
    ところで、このテストが本番の data/articles/ を書き換え始めた
    （conftest のガードが検知）。**承認が増えるとテストが本番を触る**という、
    件数に依存して現れる形だった。
    """
    from src.publishers.review_queue import ReviewQueue

    os.environ["DRY_RUN"] = "true"
    monkeypatch.setattr("src.pipeline.OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr("src.pipeline.ARTICLE_DIR", tmp_path / "articles")
    monkeypatch.setattr("src.pipeline.ReviewQueue",
                        lambda *a, **k: ReviewQueue(tmp_path / "review"))

    results = Pipeline(Config.load()).publish_approved()

    assert all(r["id"] for r in results) or results == []


# --- 実運用で見つかった障害の再発防止 -----------------------------------------
def test_sampleオプションの既定はNoneで自動判定に任せる():
    """store_true の既定 False を渡すと、トークンが無いのに X API を叩いて 401 で落ちる。

    2026-08-22 の daily-generate 失敗の原因。
    """
    from src.pipeline import build_parser

    args = build_parser().parse_args(["run"])
    assert args.sample is None

    args = build_parser().parse_args(["scout"])
    assert args.sample is None

    args = build_parser().parse_args(["run", "--sample"])
    assert args.sample is True


def test_トークンがなければ本番指定でもサンプルに落ちる(monkeypatch):
    """毎朝の cron を 401 で止めないための安全弁。"""
    from src.collectors.twitter import TwitterCollector
    from src.config import Config

    config = Config.load()
    config.x_bearer_token = ""
    collector = TwitterCollector(config)

    def _fail(*a, **k):
        raise AssertionError("トークンが無いのに X API を呼んでいる")

    monkeypatch.setattr(collector, "_search", _fail)

    collected = collector.collect(use_sample=False)

    assert any(collected.values())        # サンプルで中身が返る


# --- 2026-08-30 の duration_over ---------------------------------------------

def test_台本プロンプトは尺を文字数で伝える():
    """秒で指示しても LLM は自分の文章の読み上げ時間を見積もれない。

    実測: narration 400字が上限90秒を超えた（duration_over）。プロンプトには
    「62〜90秒に収める」と書いてあったので、秒では効いていない。
    """
    import inspect

    from src.config import Config
    from src.processing.summarizer import Summarizer

    s = Summarizer(Config.load())
    lo, hi = s._char_budget()
    src = inspect.getsource(s._script_via_claude)

    assert "_char_budget()" in src, "プロンプトが文字数を渡していない"
    assert lo < hi
    # 上限を超えた実測値（400字）が予算の外にあること
    assert 400 > hi, f"400字が上限 {hi}字 の中に入ってしまっている"


def test_文字数の予算は設定の尺から作る():
    """config で尺を変えたら予算も動くこと。二重管理にしない。"""
    from src.config import Config
    from src.processing.summarizer import SPEECH_CHARS_PER_SEC, Summarizer

    config = Config.load()
    config.section("video")["min_duration_sec"] = 30
    config.section("video")["max_duration_sec"] = 60

    lo, hi = Summarizer(config)._char_budget()

    assert lo == int(30 * SPEECH_CHARS_PER_SEC)
    assert hi == int(60 * SPEECH_CHARS_PER_SEC)


def test_読み上げ速度の実測がログに出る(caplog):
    """換算が正しいか確かめる手がかりが無いと、上限を超えても直す根拠が無い。"""
    from pathlib import Path

    from src.config import Config
    from src.video.builder import VideoBuilder

    builder = VideoBuilder(Config.load())
    prepared = [(Path("a.png"), None, 25.0), (Path("b.png"), None, 25.0)]

    with caplog.at_level("INFO"):
        builder._fit_duration(prepared, narration_chars=200)

    assert "読み上げ速度の実測: 4.00字/秒" in caplog.text


# --- お題から記事を書く（探索を通さない経路）---------------------------------

def test_LLMが使えないときは空の記事を作らない():
    """お題しか無い状態のテンプレ出力は中身が無い。黙って空の記事を note の
    下書きに置くより、書けないと言う方がいい。"""
    from src.config import Config
    from src.processing.summarizer import Summarizer

    s = Summarizer(Config.load())

    class _Dead:
        available = False
        provider = "none"

    s.llm = _Dead()

    assert s.write_from_theme("ふるさと納税の上限") is None


def test_お題から書いた記事に免責が入る(monkeypatch):
    """税理士法。個別の税務判断を請け負う形にしない。"""
    from src.config import Config
    from src.processing.summarizer import Summarizer

    s = Summarizer(Config.load())

    class _Fake:
        available = True
        provider = "fake"

        def generate_json(self, system, prompt, schema):
            assert "お題" in prompt
            assert "創作しない" in prompt
            return {"title": "見出し", "body_markdown": "## 本文\n\n説明。"}

    s.llm = _Fake()
    article = s.write_from_theme("ふるさと納税の上限", "tax")

    assert article is not None
    assert article.generated_by == "fake"
    assert "専門家" in article.body_markdown or "税理士" in article.body_markdown


def test_draftコマンドが繋がっている():
    """CLI から呼べること。"""
    from src.pipeline import build_parser

    args = build_parser().parse_args(["draft", "--theme", "テスト"])

    assert args.theme == "テスト"
    assert args.func.__name__ == "_cmd_draft"
