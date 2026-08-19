"""スライド画像 + TTS 音声から縦型 (9:16) ショート動画を生成。

- スライド画像: Pillow で生成
- 音声: gTTS（オンライン）で各ナレーションを mp3 化
- 合成: ffmpeg を subprocess で呼び出し、スライドを音声長に合わせて連結

依存が未インストール、または生成に失敗した場合は、スクリプトを JSON として
書き出す「絵コンテのみ」モードにフォールバックする（パイプラインは止めない）。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from ..config import Config
from ..models import VideoScript

logger = logging.getLogger(__name__)


class VideoBuilder:
    def __init__(self, config: Config):
        self.config = config
        v = config.section("video")
        self.width = int(v.get("width", 1080))
        self.height = int(v.get("height", 1920))
        self.bg = v.get("background_color", "#0f172a")
        self.fg = v.get("text_color", "#f8fafc")
        self.accent = v.get("accent_color", "#38bdf8")
        self.tts_lang = v.get("tts_lang", "ja")
        # TikTok Creator Rewards の対象は1分以上の動画。これを下回ると収益化されない。
        self.min_duration = int(v.get("min_duration_sec", 62))
        self.max_duration = int(v.get("max_duration_sec", 90))

    def build(self, script: VideoScript, out_path: Path) -> Path:
        """動画を生成して out_path (mp4) を返す。失敗時は storyboard(json) を返す。"""
        if not self._ffmpeg_available():
            logger.warning("ffmpeg が見つかりません。絵コンテJSONを出力します。")
            return self._storyboard_fallback(script, out_path)

        try:
            return self._render(script, out_path)
        except Exception as exc:  # pragma: no cover - 環境依存
            logger.warning("動画生成に失敗（%s）。絵コンテJSONにフォールバックします。", exc)
            return self._storyboard_fallback(script, out_path)

    # ------------------------------------------------------------------
    def _render(self, script: VideoScript, out_path: Path) -> Path:
        from PIL import Image, ImageDraw, ImageFont  # 遅延 import

        try:
            from gtts import gTTS
        except ImportError:
            gTTS = None  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # まず各スライドの画像と音声を作り、尺を確定させる。
            # 合計尺が min_duration に届かない場合は最後のスライドを延長する
            # （1分未満だと TikTok Creator Rewards の対象外になるため）。
            prepared: list[tuple[Path, Path | None, float]] = []
            for i, (slide, narration) in enumerate(
                zip(script.slides, script.narration)
            ):
                img_path = tmpdir / f"slide_{i:02d}.png"
                self._draw_slide(img_path, slide, i, Image, ImageDraw, ImageFont)

                # 音声（無ければ無音3秒）
                dur = 3.0
                audio_path: Path | None = tmpdir / f"audio_{i:02d}.mp3"
                if gTTS is not None:
                    gTTS(text=narration, lang=self.tts_lang).save(str(audio_path))
                    dur = self._audio_duration(audio_path)
                else:
                    audio_path = None
                prepared.append((img_path, audio_path, dur))

            prepared = self._fit_duration(prepared)

            concat_lines: list[str] = []
            for i, (img_path, audio_path, dur) in enumerate(prepared):
                clip_path = tmpdir / f"clip_{i:02d}.mp4"
                self._make_clip(img_path, audio_path, dur, clip_path)
                concat_lines.append(f"file '{clip_path.as_posix()}'")

            concat_file = tmpdir / "concat.txt"
            concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

            out_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(concat_file), "-c", "copy", str(out_path)],
                check=True, capture_output=True,
            )
        logger.info("動画を生成しました: %s", out_path)
        return out_path

    def _fit_duration(self, prepared: list[tuple[Path, Path | None, float]]
                      ) -> list[tuple[Path, Path | None, float]]:
        """合計尺を [min_duration, max_duration] に寄せる。

        不足分は最終スライドを延長して埋める（尺稼ぎのために内容を薄めるのではなく、
        まとめスライドの表示時間を伸ばす）。超過している場合は警告のみ出す。
        """
        if not prepared:
            return prepared

        total = sum(d for _, _, d in prepared)
        if total < self.min_duration:
            deficit = self.min_duration - total
            img, audio, dur = prepared[-1]
            prepared[-1] = (img, audio, dur + deficit)
            logger.info("合計尺 %.1f秒 → %.1f秒に延長しました（min_duration_sec=%d）",
                        total, total + deficit, self.min_duration)
        elif total > self.max_duration:
            logger.warning("合計尺が %.1f秒で max_duration_sec=%d を超えています。"
                           "narration を短くするか slides_per_video を減らしてください。",
                           total, self.max_duration)
        return prepared

    def _draw_slide(self, path: Path, text: str, index: int,
                    Image, ImageDraw, ImageFont) -> None:
        img = Image.new("RGB", (self.width, self.height), self.bg)
        draw = ImageDraw.Draw(img)
        font = self._load_font(ImageFont, size=64 if index else 80)

        wrapped = "\n".join(textwrap.wrap(text, width=14))
        # ざっくり中央寄せ
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=20)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) / 2
        y = (self.height - th) / 2
        # タイトルスライドはアクセント色
        color = self.accent if index == 0 else self.fg
        draw.multiline_text((x, y), wrapped, font=font, fill=color,
                            align="center", spacing=20)
        img.save(path)

    @staticmethod
    def _load_font(ImageFont, size: int):
        # 日本語対応フォントを順に試す
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        ]
        for c in candidates:
            if Path(c).exists():
                try:
                    return ImageFont.truetype(c, size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def _make_clip(self, img_path: Path, audio_path, dur: float, out: Path) -> None:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path)]
        if audio_path is not None:
            cmd += ["-i", str(audio_path)]
        cmd += [
            "-c:v", "libx264", "-t", f"{dur:.2f}", "-pix_fmt", "yuv420p",
            "-vf", f"scale={self.width}:{self.height}",
        ]
        if audio_path is not None:
            cmd += ["-c:a", "aac", "-shortest"]
        cmd.append(str(out))
        subprocess.run(cmd, check=True, capture_output=True)

    @staticmethod
    def _audio_duration(path: Path) -> float:
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                check=True, capture_output=True, text=True,
            )
            return max(2.0, float(out.stdout.strip()))
        except Exception:
            return 3.0

    @staticmethod
    def _ffmpeg_available() -> bool:
        return shutil.which("ffmpeg") is not None

    def _storyboard_fallback(self, script: VideoScript, out_path: Path) -> Path:
        sb_path = out_path.with_suffix(".storyboard.json")
        sb_path.parent.mkdir(parents=True, exist_ok=True)
        sb_path.write_text(
            json.dumps(script.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("絵コンテを出力しました: %s", sb_path)
        return sb_path
