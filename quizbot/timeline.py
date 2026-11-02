"""구간 길이 계산. 오디오 길이만 받아 계산하는 순수 로직."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from config import VideoConfig
from quizbot.models import Segment

logger = logging.getLogger(__name__)

_GAP = 0.3  # 나레이션/소리 뒤 여유


@dataclass(frozen=True)
class QuizDurations:
    question_tts: float
    reveal_tts: float
    animal_sound: float = 0.0  # 0이면 소리 없음


@dataclass(frozen=True)
class EpisodeDurations:
    hook_tts: float
    outro_tts: float
    quizzes: tuple[QuizDurations, ...]


@dataclass(frozen=True)
class SegmentLengths:
    hook: float
    questions: list[float]
    reveals: list[float]
    outro: float
    countdown: float

    @property
    def total(self) -> float:
        n = len(self.questions)
        return self.hook + sum(self.questions) + sum(self.reveals) + n * self.countdown + self.outro


def question_length(q: QuizDurations, cfg: VideoConfig) -> float:
    length = cfg.narration_lead_sec + q.question_tts + _GAP
    if q.animal_sound > 0:
        length += min(q.animal_sound, cfg.animal_sound_max_sec) + _GAP
    return length


def base_lengths(d: EpisodeDurations, cfg: VideoConfig) -> SegmentLengths:
    lead = cfg.narration_lead_sec
    outro_need = lead + d.outro_tts + _GAP
    return SegmentLengths(
        hook=max(cfg.hook_sec, lead + d.hook_tts + _GAP),
        questions=[question_length(q, cfg) for q in d.quizzes],
        reveals=[max(cfg.reveal_min_sec, cfg.reveal_narration_delay_sec + q.reveal_tts + 0.6) for q in d.quizzes],
        outro=max(outro_need, min(cfg.outro_max_sec, max(cfg.outro_min_sec, outro_need + 0.3))),
        countdown=cfg.countdown_sec,
    )


def fit_quiz_count(d: EpisodeDurations, cfg: VideoConfig) -> int:
    """최대 길이를 넘으면 뒤쪽 퀴즈부터 뺀다. 남길 퀴즈 개수를 돌려준다."""
    n = len(d.quizzes)
    while n > cfg.min_quizzes:
        trimmed = EpisodeDurations(d.hook_tts, d.outro_tts, d.quizzes[:n])
        if base_lengths(trimmed, cfg).total <= cfg.max_total_sec:
            break
        n -= 1
    return n


def pad_to_minimum(lengths: SegmentLengths, cfg: VideoConfig) -> SegmentLengths:
    deficit = cfg.min_total_sec - lengths.total
    if deficit <= 0 or not lengths.reveals:
        return lengths
    per_reveal = min(1.5, deficit / len(lengths.reveals))
    reveals = [r + per_reveal for r in lengths.reveals]
    deficit -= per_reveal * len(reveals)
    outro = lengths.outro
    if deficit > 0:
        extra = max(0.0, min(deficit, cfg.outro_max_sec - outro))
        outro += extra
        deficit -= extra
    padded = SegmentLengths(lengths.hook, lengths.questions, reveals, outro, lengths.countdown)
    if deficit > 0.01:
        logger.warning("영상 길이 %.1f초로 최소 %.0f초보다 짧습니다.", padded.total, cfg.min_total_sec)
    return padded


def build_timeline(d: EpisodeDurations, cfg: VideoConfig) -> list[Segment]:
    lengths = pad_to_minimum(base_lengths(d, cfg), cfg)
    if lengths.total > cfg.max_total_sec:
        logger.warning("영상 길이 %.1f초로 최대 %.0f초를 넘습니다.", lengths.total, cfg.max_total_sec)
    segments: list[Segment] = []
    t = 0.0

    def push(kind: str, duration: float, idx: int | None = None) -> None:
        nonlocal t
        segments.append(Segment(kind, round(t, 3), round(duration, 3), idx))
        t += duration

    push("hook", lengths.hook)
    for i, (q_len, r_len) in enumerate(zip(lengths.questions, lengths.reveals)):
        push("question", q_len, i)
        push("countdown", lengths.countdown, i)
        push("reveal", r_len, i)
    push("outro", lengths.outro)
    return segments
