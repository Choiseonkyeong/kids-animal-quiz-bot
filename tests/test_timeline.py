from __future__ import annotations

from config import VideoConfig
from quizbot.timeline import EpisodeDurations, QuizDurations, build_timeline, fit_quiz_count

CFG = VideoConfig()


def _ep(n: int, q: float = 2.0, r: float = 1.2, sound: float = 0.0) -> EpisodeDurations:
    return EpisodeDurations(2.0, 2.5, tuple(QuizDurations(q, r, sound) for _ in range(n)))


def test_structure_and_bounds() -> None:
    segs = build_timeline(_ep(5), CFG)
    kinds = [s.kind for s in segs]
    assert kinds[0] == "hook" and kinds[-1] == "outro"
    assert kinds[1:4] == ["question", "countdown", "reveal"]
    assert all(s.duration == 3.0 for s in segs if s.kind == "countdown")
    assert segs[0].duration >= 3.0
    assert CFG.outro_min_sec <= segs[-1].duration <= CFG.outro_max_sec
    assert CFG.min_total_sec <= segs[-1].end <= CFG.max_total_sec
    for a, b in zip(segs, segs[1:]):
        assert abs(a.end - b.start) < 1e-6


def test_short_episode_is_padded_to_minimum() -> None:
    segs = build_timeline(_ep(4, q=1.0, r=0.8), CFG)
    assert segs[-1].end >= CFG.min_total_sec - 0.01


def test_long_episode_drops_last_quiz() -> None:
    d = _ep(5, q=3.0, r=1.5, sound=4.0)
    n = fit_quiz_count(d, CFG)
    assert 3 <= n < 5
    trimmed = EpisodeDurations(d.hook_tts, d.outro_tts, d.quizzes[:n])
    assert build_timeline(trimmed, CFG)[-1].end <= CFG.max_total_sec
