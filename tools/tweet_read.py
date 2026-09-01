#!/usr/bin/env python3
"""ツイート（と手元のメディア）を Claude が読める形に落とす。

**なぜ要るか。** このリポジトリのクラウドセッションからは `x.com` も
`pbs.twimg.com` も egress ポリシーで塞がれていて、ツイートの画像や動画を
そのままでは開けない。動画はそもそも「見る」ことができず、コマ（静止画）に
割らないと読めない。

**このプロジェクトのパイプラインとは無関係。** 副業パイプライン
（`src/`）は一切呼ばないし、`CLAUDE.md` の凍結対象にも触れない。
オーナーが Claude Code に X の投稿を読ませるための道具。

使い方:

    python tools/tweet_read.py https://x.com/user/status/123456789
    python tools/tweet_read.py 123456789
    python tools/tweet_read.py ./screenshot.png       # 手元のファイルでもよい
    python tools/tweet_read.py ./demo.mp4 --frames 12

出力は `data/inbox/<id>/` に落ちる。最後に「これを Read しろ」という
ファイル一覧を出すので、Claude はそれを開けばよい。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 埋め込み用の公開エンドポイント。2026-09-01 時点でこのホストだけ通る
# （x.com / api.x.com / pbs.twimg.com / video.twimg.com はいずれも
# gateway が CONNECT に 403 を返す）。
SYNDICATION = "https://cdn.syndication.twimg.com/tweet-result?id={id}&lang=ja&token=a"

OUT_ROOT = Path(__file__).resolve().parent.parent / "data" / "inbox"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def tweet_id(arg: str) -> str | None:
    """URL でも ID でも受ける。ファイルパスなら None。"""
    if Path(arg).exists():
        return None
    m = re.search(r"status(?:es)?/(\d+)", arg)
    if m:
        return m.group(1)
    return arg if arg.isdigit() else None


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def media_urls(payload: dict) -> list[str]:
    """写真・動画・GIF の実体 URL を集める。"""
    urls: list[str] = []
    for photo in payload.get("photos") or []:
        if photo.get("url"):
            urls.append(photo["url"])
    for video in payload.get("mediaDetails") or []:
        variants = video.get("video_info", {}).get("variants", [])
        mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
        if mp4s:
            # 一番ビットレートの高いものを取る（コマに割るので画質が効く）
            urls.append(max(mp4s, key=lambda v: v.get("bitrate", 0))["url"])
        elif video.get("media_url_https"):
            urls.append(video["media_url_https"])
    article = payload.get("article") or {}
    cover = article.get("cover_media", {}).get("media_info", {}).get("original_img_url")
    if cover:
        urls.append(cover)
    return urls


def download(url: str, dest: Path) -> Path | None:
    """落とせたらパス、ポリシーで塞がれていたら None。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        return dest
    except (urllib.error.URLError, OSError) as exc:
        host = urllib.parse.urlsplit(url).netloc
        print(f"  × 取得できません: {host}\n    {exc}", file=sys.stderr)
        return None


def ffmpeg_exe() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def extract_frames(video: Path, out_dir: Path, count: int) -> list[Path]:
    """動画を等間隔のコマに割る。**動画は見られないがコマなら読める。**"""
    exe = ffmpeg_exe()
    if not exe:
        print("  × ffmpeg がありません: pip install imageio-ffmpeg", file=sys.stderr)
        return []

    probe = subprocess.run(
        [exe, "-i", str(video)], capture_output=True, text=True
    ).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe)
    seconds = 0.0
    if m:
        seconds = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%03d.png")
    if seconds > 0:
        fps = max(count / seconds, 0.05)
        args = ["-vf", f"fps={fps}", "-frames:v", str(count)]
    else:
        args = ["-frames:v", str(count)]

    subprocess.run([exe, "-y", "-i", str(video), *args, "-vsync", "vfr", pattern],
                   capture_output=True, text=True)
    return sorted(out_dir.glob("frame_*.png"))


def summarize(payload: dict) -> str:
    user = payload.get("user", {})
    lines = [
        f"投稿者 : {user.get('name','?')} (@{user.get('screen_name','?')})",
        f"日時   : {payload.get('created_at','?')}",
        f"いいね : {payload.get('favorite_count','?')}",
        f"返信   : {payload.get('conversation_count','?')}",
        "本文   :",
        (payload.get("text") or "").strip() or "（本文なし）",
    ]
    article = payload.get("article") or {}
    if article:
        lines += [
            "",
            "X Articles へのリンク（本文は x.com 側にあり、ここからは読めない）:",
            f"  タイトル: {article.get('title','?')}",
            f"  冒頭    : {(article.get('preview_text') or '').strip()}",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="ツイート/メディアを Claude が読める形にする")
    ap.add_argument("target", help="ツイートURL / ツイートID / 手元の画像・動画のパス")
    ap.add_argument("--frames", type=int, default=8, help="動画から取るコマ数（既定8）")
    args = ap.parse_args()

    local = Path(args.target)
    tid = tweet_id(args.target)

    readable: list[Path] = []

    if tid is None and local.exists():
        out_dir = OUT_ROOT / local.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        if local.suffix.lower() in VIDEO_SUFFIXES:
            frames = extract_frames(local, out_dir / "frames", args.frames)
            readable.extend(frames)
        else:
            copied = out_dir / local.name
            shutil.copy(local, copied)
            readable.append(copied)
    elif tid:
        out_dir = OUT_ROOT / tid
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = fetch_json(SYNDICATION.format(id=tid))
        (out_dir / "tweet.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        text = summarize(payload)
        (out_dir / "tweet.txt").write_text(text, encoding="utf-8")
        print(text)
        print()

        urls = media_urls(payload)
        if not urls:
            print("メディアなし。")
        for i, url in enumerate(urls, 1):
            suffix = Path(urllib.parse.urlsplit(url).path).suffix or ".bin"
            got = download(url, out_dir / f"media_{i}{suffix}")
            if not got:
                continue
            if suffix.lower() in VIDEO_SUFFIXES:
                readable.extend(extract_frames(got, out_dir / f"frames_{i}", args.frames))
            else:
                readable.append(got)
    else:
        print(f"ツイートIDもファイルも見つかりません: {args.target}", file=sys.stderr)
        return 2

    print("\n--- Claude が Read するファイル ---")
    if readable:
        for path in readable:
            print(path)
    else:
        print("（なし）画像・動画が取れていません。"
              "x.com / pbs.twimg.com / video.twimg.com が egress ポリシーで"
              "塞がれている場合は、環境のネットワーク設定を変えるか、"
              "ファイルを直接チャットに添付してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
