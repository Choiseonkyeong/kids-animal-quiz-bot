"""MoviePy로 타임라인을 영상으로 합성한다."""
from __future__ import annotations

import logging
import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from moviepy import AudioClip, AudioFileClip, CompositeAudioClip, VideoClip
from moviepy.audio import fx as afx
from PIL import Image

from config import AppConfig
from quizbot.errors import RenderError
from quizbot.frames import FramePainter, FrameSpec
from quizbot.models import EpisodeAssets, Segment
from quizbot.series import SeriesInfo

logger = logging.getLogger(__name__)

def audio_duration(path: Path) -> float:
    try:
        clip = AudioFileClip(str(path))
    except (OSError, KeyError, ValueError) as exc:
        raise RenderError(f"오디오 파일을 읽지 못했습니다: {path} ({exc})") from exc
    try:
        return float(clip.duration)
    finally:
        clip.close()


_BOUNCE_PX = 18.0
_BOUNCE_HZ = 1.2


@dataclass(frozen=True)
class _Sprite:
    rgb: np.ndarray  # (h, w, 3) float32
    alpha: np.ndarray  # (h, w, 1) float32, 0~1
    left: int
    top: int

    @staticmethod
    def from_spec(spec: FrameSpec) -> _Sprite | None:
        if spec.sprite is None:
            return None
        arr = np.asarray(spec.sprite, dtype=np.float32)
        w, h = spec.sprite.size
        cx, cy = spec.sprite_center
        return _Sprite(arr[..., :3], arr[..., 3:4] / 255.0, cx - w // 2, cy - h // 2)


@dataclass(frozen=True)
class _Layer:
    """[start, end) 동안 보이는 정지 배경 + (선택) 통통 튀는 스프라이트."""

    start: float
    end: float
    base: np.ndarray  # (H, W, 3) uint8
    sprite: _Sprite | None = None

    def render(self, local_t: float) -> np.ndarray:
        if self.sprite is None:
            return self.base
        s = self.sprite
        frame = self.base.copy()
        h, w = s.alpha.shape[:2]
        top = s.top + int(round(_BOUNCE_PX * math.sin(2 * math.pi * _BOUNCE_HZ * local_t)))
        # 화면 밖으로 나가는 부분은 잘라낸다
        y0, y1 = max(0, top), min(frame.shape[0], top + h)
        x0, x1 = max(0, s.left), min(frame.shape[1], s.left + w)
        if y0 >= y1 or x0 >= x1:
            return frame
        sy, sx = y0 - top, x0 - s.left
        alpha = s.alpha[sy : sy + y1 - y0, sx : sx + x1 - x0]
        region = frame[y0:y1, x0:x1].astype(np.float32)
        blended = region * (1 - alpha) + s.rgb[sy : sy + y1 - y0, sx : sx + x1 - x0] * alpha
        frame[y0:y1, x0:x1] = blended.astype(np.uint8)
        return frame


class EpisodeRenderer:
    def __init__(self, cfg: AppConfig, series: SeriesInfo, assets: EpisodeAssets) -> None:
        self._cfg = cfg
        self._series = series
        self._assets = assets
        self._painter = FramePainter(cfg.font, cfg.video, assets.logo)
        self._opened: list[AudioFileClip] = []

    # ---------- 화면 ----------
    def _color(self, index: int) -> str:
        palette = self._cfg.style.palette
        return palette[index % len(palette)]

    def _layers(self, seg: Segment, spec: FrameSpec) -> list[_Layer]:
        return [_Layer(seg.start, seg.end, np.array(spec.base.convert("RGB")), _Sprite.from_spec(spec))]

    def _countdown_layers(self, question: FrameSpec, seg: Segment) -> list[_Layer]:
        step = seg.duration / 3
        return [
            _Layer(seg.start + k * step, seg.start + (k + 1) * step, np.array(self._painter.countdown(question, n)))
            for k, n in enumerate((3, 2, 1))
        ]

    def _build_layers(self, segments: Sequence[Segment]) -> list[_Layer]:
        channel = self._cfg.channel.name
        layers: list[_Layer] = []
        question_specs: dict[int, FrameSpec] = {}
        for seg in segments:
            i = seg.quiz_index
            if seg.kind == "hook":
                layers += self._layers(seg, self._painter.hook(channel, self._series.name, self._color(0)))
            elif seg.kind == "question" and i is not None:
                qa = self._assets.quizzes[i]
                spec = self._painter.question(i + 1, self._series.question_caption, qa.question_image, self._color(i + 1))
                question_specs[i] = spec
                layers += self._layers(seg, spec)
            elif seg.kind == "countdown" and i is not None:
                layers += self._countdown_layers(question_specs[i], seg)
            elif seg.kind == "reveal" and i is not None:
                qa = self._assets.quizzes[i]
                layers += self._layers(seg, self._painter.reveal(qa.quiz.answer, qa.reveal_image, self._color(i + 1), i + 1))
            elif seg.kind == "outro":
                layers += self._layers(seg, self._painter.outro(channel, self._color(len(segments))))
        return layers

    def _video_clip(self, segments: Sequence[Segment], total: float) -> VideoClip:
        layers = self._build_layers(segments)
        starts = [layer.start for layer in layers]

        def frame(t: float) -> np.ndarray:
            layer = layers[max(0, bisect_right(starts, t) - 1)]
            return layer.render(t - layer.start)

        return VideoClip(frame_function=frame, duration=total)

    # ---------- 소리 ----------
    def _audio(self, path: Path, start: float, volume: float = 1.0, max_len: float | None = None) -> AudioFileClip:
        clip = AudioFileClip(str(path))
        self._opened.append(clip)
        if max_len is not None and clip.duration > max_len:
            clip = clip.subclipped(0, max_len).with_effects([afx.AudioFadeOut(0.3)])
        return clip.with_start(start).with_volume_scaled(volume)

    def _audio_clips(self, segments: Sequence[Segment], total: float) -> list[AudioClip]:
        v = self._cfg.video
        a = self._assets
        lead = v.narration_lead_sec
        clips: list[AudioClip] = []
        for seg in segments:
            i = seg.quiz_index
            if seg.kind == "hook":
                clips.append(self._audio(a.hook_tts, seg.start + lead))
            elif seg.kind == "question" and i is not None:
                qa = a.quizzes[i]
                q_clip = self._audio(qa.question_tts, seg.start + lead)
                clips.append(q_clip)
                if qa.animal_sound is not None:
                    sound_start = seg.start + lead + q_clip.duration + 0.3
                    clips.append(self._audio(qa.animal_sound, sound_start, v.animal_sound_volume, v.animal_sound_max_sec))
            elif seg.kind == "countdown" and a.countdown_sfx is not None:
                step = seg.duration / 3
                clips += [self._audio(a.countdown_sfx, seg.start + k * step, v.sfx_volume, step) for k in range(3)]
            elif seg.kind == "reveal" and i is not None:
                if a.reveal_sfx is not None:
                    clips.append(self._audio(a.reveal_sfx, seg.start, v.sfx_volume, seg.duration))
                clips.append(self._audio(a.quizzes[i].reveal_tts, seg.start + v.reveal_narration_delay_sec))
            elif seg.kind == "outro":
                clips.append(self._audio(a.outro_tts, seg.start + lead))
        if a.bgm is not None:
            clips.append(self._bgm(a.bgm, total))
        return clips

    def _bgm(self, path: Path, total: float) -> AudioClip:
        clip = AudioFileClip(str(path))
        self._opened.append(clip)
        return clip.with_effects(
            [afx.AudioLoop(duration=total), afx.AudioFadeOut(1.5)]
        ).with_volume_scaled(self._cfg.video.bgm_volume)

    # ---------- 출력 ----------
    def render(self, segments: Sequence[Segment], out: Path) -> Path:
        if not segments:
            raise RenderError("타임라인이 비었습니다.")
        total = segments[-1].end
        v = self._cfg.video
        try:
            video = self._video_clip(segments, total)
            audio = CompositeAudioClip(self._audio_clips(segments, total)).with_duration(total)
            video = video.with_audio(audio)
            video.write_videofile(
                str(out),
                fps=v.fps,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                pixel_format="yuv420p",
                threads=4,
                logger=None,
            )
        except (OSError, ValueError, KeyError) as exc:
            raise RenderError(f"영상 렌더링 실패: {exc}") from exc
        finally:
            for clip in self._opened:
                clip.close()
            self._opened.clear()
        logger.info("영상 저장: %s (%.1f초)", out, total)
        return out

    def render_thumbnail(self, out: Path) -> Path:
        first = self._assets.quizzes[0]
        img: Image.Image = self._painter.thumbnail(
            self._series.name, self._cfg.channel.name, first.question_image, self._color(1)
        )
        img.save(out)
        return out
