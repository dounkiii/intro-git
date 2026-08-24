

def test_広告表示は説明文の先頭に出る(monkeypatch):
    """景表法のステマ規制で求められるのは「一般消費者が広告だと明瞭に分かる」
    こと。末尾に置くとリンクや免責の後ろに埋もれる。"""
    monkeypatch.setenv("AFF_HUB_URL", "https://example.com/hub")
    from src.config import Config
    from src.models import Topic, Tweet
    from src.processing.summarizer import Summarizer

    config = Config.load()
    summarizer = Summarizer(config)
    block = summarizer.affiliate.build("tax")
    topic = Topic(category="tax", headline="見出し", score=1.0, tweets=[
        Tweet(id="1", text="本文", author="a", url="https://example.com",
              created_at="", likes=1, retweets=0, replies=0)])

    desc = summarizer._compose_description("本文です", topic, block)
    disclosure = config.section("monetization")["disclosure"]

    assert desc.startswith(disclosure)
    assert desc.count(disclosure) == 1      # フッタと二重に出さない


def test_換金経路が無ければ広告表示は出さない():
    """リンクが1つも無い投稿に「アフィリエイトリンクを含みます」と書くのは
    それ自体が誤表示になる。"""
    from src.config import Config
    from src.monetize.affiliate import AffiliateEngine

    engine = AffiliateEngine(Config.load())
    block = engine.build("tax", quiet=True)

    assert not block.has_route
    assert engine.disclosure_header(block) == ""
