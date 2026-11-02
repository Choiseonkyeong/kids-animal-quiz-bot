from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# question_visual: 질문 구간 이미지를 무엇으로 만들지
#   silhouette = 동물 이미지를 검은 실루엣으로 (정답 노출 방지)
#   hint       = hint_visual 설명으로 생성한 이미지
# reveal_subject: 정답 구간 이미지 주제
#   animal = quiz.animal, answer = quiz.answer, hint = 질문 이미지 재사용
QuestionVisual = Literal["silhouette", "hint"]
RevealSubject = Literal["animal", "answer", "hint"]


@dataclass(frozen=True)
class SeriesInfo:
    key: str
    name: str
    question_caption: str  # 질문 구간에 크게 띄울 핵심 단어
    question_visual: QuestionVisual
    reveal_subject: RevealSubject
    requires_animal_sound: bool = False


SERIES: dict[str, SeriesInfo] = {
    "sound": SeriesInfo("sound", "누구 소리일까?", "누구 소리?", "silhouette", "animal", requires_animal_sound=True),
    "footprint": SeriesInfo("footprint", "누구 발자국일까?", "누구일까?", "hint", "animal"),
    "baby": SeriesInfo("baby", "아기 이름은?", "아기 이름은?", "hint", "answer"),
    "count": SeriesInfo("count", "동물이랑 숫자·색깔", "몇 마리? 무슨 색?", "hint", "hint"),
    "food": SeriesInfo("food", "뭐 먹고 살까?", "뭐 먹을까?", "hint", "answer"),
}


def get_series(key: str) -> SeriesInfo:
    try:
        return SERIES[key]
    except KeyError as exc:
        raise ValueError(f"알 수 없는 시리즈: {key!r} (가능: {', '.join(SERIES)})") from exc
