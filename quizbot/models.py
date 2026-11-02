from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Quiz:
    question: str
    answer: str
    animal: str
    hint_visual: str


@dataclass(frozen=True)
class Script:
    series: str
    title: str
    hook: str
    quizzes: tuple[Quiz, ...]
    outro: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quizzes"] = [asdict(q) for q in self.quizzes]
        return data

    def with_quizzes(self, quizzes: list[Quiz]) -> Script:
        return Script(self.series, self.title, self.hook, tuple(quizzes), self.outro)


@dataclass(frozen=True)
class QuizAssets:
    """퀴즈 1개를 렌더링하는 데 필요한 파일."""

    quiz: Quiz
    question_image: Path | None
    reveal_image: Path | None
    question_tts: Path
    reveal_tts: Path
    animal_sound: Path | None = None


@dataclass(frozen=True)
class EpisodeAssets:
    script: Script
    hook_tts: Path
    outro_tts: Path
    quizzes: tuple[QuizAssets, ...]
    bgm: Path | None
    logo: Path | None
    countdown_sfx: Path | None
    reveal_sfx: Path | None


@dataclass(frozen=True)
class Segment:
    """타임라인 한 구간."""

    kind: str  # hook | question | countdown | reveal | outro
    start: float
    duration: float
    quiz_index: int | None = None

    @property
    def end(self) -> float:
        return self.start + self.duration
