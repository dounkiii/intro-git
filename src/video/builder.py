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
import re
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
        self.sub = v.get("sub_color", "#94a3b8")
        self.tts_lang = v.get("tts_lang", "ja")
        self.max_duration = int(v.get("max_duration_sec", 55))
        self.handle = v.get("handle", "")          # 例: @your_handle（画面下に表示）
        self.footer_note = v.get("footer_note", "※投資は自己責任・税制は要確認")

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
            concat_lines: list[str] = []

            for i, (slide, narration) in enumerate(
                zip(script.slides, script.narration)
            ):
                img_path = tmpdir / f"slide_{i:02d}.png"
                self._draw_slide(img_path, slide, i, len(script.slides),
                                 Image, ImageDraw, ImageFont)

                # 音声（無ければ無音3秒）
                dur = 3.0
                audio_path = tmpdir / f"audio_{i:02d}.mp3"
                if gTTS is not None:
                    gTTS(text=narration, lang=self.tts_lang).save(str(audio_path))
                    dur = self._audio_duration(audio_path)
                else:
                    audio_path = None  # type: ignore

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

    def _draw_slide(self, path: Path, text: str, index: int, total: int,
                    Image, ImageDraw, ImageFont) -> None:
        img = Image.new("RGB", (self.width, self.height), self.bg)
        draw = ImageDraw.Draw(img)

        is_hook = index == 0
        is_cta = index == total - 1
        is_point = bool(re.match(r"^\d+[\.\．]", text.strip()))
        role = "POINT" if is_point else ("HOOK" if is_hook else ("NEXT" if is_cta else "SUMMARY"))

        # 上部プログレスバー（何枚目か）
        self._progress_bar(draw, index, total)

        # 役割チップ（左上）
        self._role_chip(draw, ImageFont, role)

        # 本文（強調色は hook/CTA/まとめ、要点は白）
        main_color = self.fg if is_point else self.accent
        font_size = 76 if (is_hook or is_cta) else 66
        font = self._load_font(ImageFont, size=font_size)
        wrapped = "\n".join(textwrap.wrap(text.replace("\n", " "), width=13))
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=22)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) / 2
        y = (self.height - th) / 2
        draw.multiline_text((x, y), wrapped, font=font, fill=main_color,
                            align="center", spacing=22)

        # 本文下のアクセント下線
        underline_y = y + th + 40
        draw.rectangle(
            [(self.width / 2 - 90, underline_y), (self.width / 2 + 90, underline_y + 8)],
            fill=self.accent,
        )

        # フッター（ハンドル + 注意書き）
        self._footer(draw, ImageFont)
        img.save(path)

    def _progress_bar(self, draw, index: int, total: int) -> None:
        margin, h, top = 60, 10, 70
        full = self.width - margin * 2
        draw.rounded_rectangle([(margin, top), (margin + full, top + h)],
                               radius=h // 2, fill=self.bg_line())
        if total > 1:
            w = full * (index + 1) / total
            draw.rounded_rectangle([(margin, top), (margin + w, top + h)],
                                   radius=h // 2, fill=self.accent)

    def _role_chip(self, draw, ImageFont, role: str) -> None:
        font = self._load_font(ImageFont, size=34)
        pad_x, pad_y, top, left = 26, 14, 120, 60
        bbox = draw.textbbox((0, 0), role, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rounded_rectangle(
            [(left, top), (left + tw + pad_x * 2, top + th + pad_y * 2)],
            radius=16, fill=self.accent,
        )
        draw.text((left + pad_x, top + pad_y - bbox[1]), role, font=font, fill=self.bg)

    def _footer(self, draw, ImageFont) -> None:
        font = self._load_font(ImageFont, size=34)
        parts = [p for p in (self.handle, self.footer_note) if p]
        if not parts:
            return
        text = "   ".join(parts)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((self.width - tw) / 2, self.height - 150), text,
                  font=font, fill=self.sub)

    @staticmethod
    def bg_line() -> str:
        return "#1e293b"

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
