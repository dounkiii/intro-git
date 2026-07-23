"""定期実行ランナー。

外部の cron / systemd timer を使えない環境向けの簡易スケジューラ。
`--interval` 秒ごとに `Pipeline.run()` を実行する（投稿はしない）。
本番では OS の cron / GitHub Actions / クラウドのスケジューラ利用を推奨。
"""
from __future__ import annotations

import argparse
import logging
import time

from .pipeline import Pipeline

logger = logging.getLogger("scheduler")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scheduler")
    parser.add_argument("--interval", type=int, default=3600, help="実行間隔（秒）")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--once", action="store_true", help="1回だけ実行して終了")
    args = parser.parse_args(argv)

    pipeline = Pipeline()
    while True:
        try:
            pipeline.run(limit=args.limit)
        except Exception:  # pragma: no cover
            logger.exception("run 中に例外が発生しました")
        if args.once:
            break
        logger.info("次の実行まで %d 秒待機", args.interval)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
