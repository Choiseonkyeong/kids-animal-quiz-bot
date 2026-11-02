"""대본 JSON 검증. 외부 의존성 없는 순수 함수만 둔다."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from typing import Any

from config import ContentRules
from quizbot.errors import ScriptValidationError
from quizbot.models import Quiz, Script

logger = logging.getLogger(__name__)

_QUIZ_KEYS: tuple[str, ...] = ("question", "answer", "animal", "hint_visual")
_TOP_KEYS: tuple[str, ...] = ("series", "title", "hook", "quizzes", "outro")
_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str) -> dict[str, Any]:
    cleaned = _CODE_FENCE.sub("", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ScriptValidationError(f"JSON 파싱 실패: {exc}") from exc
    if not isinstance(data, dict):
        raise ScriptValidationError("최상위 JSON이 객체가 아닙니다.")
    return data


def _require_str(obj: dict[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ScriptValidationError(f"{where}.{key} 값이 비었거나 문자열이 아닙니다.")
    return value.strip()


def build_script(data: dict[str, Any]) -> Script:
    missing = [k for k in _TOP_KEYS if k not in data]
    if missing:
        raise ScriptValidationError(f"필수 키 누락: {missing}")
    raw_quizzes = data["quizzes"]
    if not isinstance(raw_quizzes, list):
        raise ScriptValidationError("quizzes가 배열이 아닙니다.")
    quizzes: list[Quiz] = []
    for i, raw in enumerate(raw_quizzes):
        if not isinstance(raw, dict):
            raise ScriptValidationError(f"quizzes[{i}]가 객체가 아닙니다.")
        quizzes.append(Quiz(*(_require_str(raw, k, f"quizzes[{i}]") for k in _QUIZ_KEYS)))
    return Script(
        series=_require_str(data, "series", "root"),
        title=_require_str(data, "title", "root"),
        hook=_require_str(data, "hook", "root"),
        quizzes=tuple(quizzes),
        outro=_require_str(data, "outro", "root"),
    )


def iter_texts(script: Script) -> Iterable[tuple[str, str]]:
    """(위치, 텍스트) 쌍을 모두 돌려준다."""
    yield "title", script.title
    yield "hook", script.hook
    for i, q in enumerate(script.quizzes):
        yield f"quizzes[{i}].question", q.question
        yield f"quizzes[{i}].answer", q.answer
        yield f"quizzes[{i}].animal", q.animal
        yield f"quizzes[{i}].hint_visual", q.hint_visual
    yield "outro", script.outro


def find_forbidden(script: Script, patterns: Sequence[str]) -> list[str]:
    compiled = [re.compile(p) for p in patterns]
    hits: list[str] = []
    for where, text in iter_texts(script):
        for pat in compiled:
            m = pat.search(text)
            if m:
                hits.append(f"{where}: '{m.group(0)}'")
    return hits


def long_sentences(script: Script, max_words: int) -> list[str]:
    spoken = [script.hook, script.outro, *(q.question for q in script.quizzes)]
    result: list[str] = []
    for text in spoken:
        for sentence in re.split(r"(?<=[.!?~])\s+", text):
            if len(sentence.split()) > max_words:
                result.append(sentence)
    return result


def validate_script(
    script: Script,
    expected_series: str,
    rules: ContentRules,
    excluded_animals: Iterable[str] = (),
) -> None:
    if script.series != expected_series:
        raise ScriptValidationError(f"series 불일치: {script.series!r} != {expected_series!r}")
    n = len(script.quizzes)
    if not rules.min_quizzes <= n <= rules.max_quizzes:
        raise ScriptValidationError(f"퀴즈 개수 {n}개 (허용 {rules.min_quizzes}~{rules.max_quizzes})")
    hits = find_forbidden(script, rules.forbidden_patterns)
    if hits:
        raise ScriptValidationError(f"금지어 포함: {hits}")
    animals = [q.animal for q in script.quizzes]
    if len(set(animals)) != len(animals):
        raise ScriptValidationError(f"한 편 안에 동물 중복: {animals}")
    excluded = set(excluded_animals)
    reused = [a for a in animals if a in excluded]
    if reused:
        raise ScriptValidationError(f"제외 목록 동물 사용: {reused}")
    for sentence in long_sentences(script, rules.max_words_per_sentence):
        logger.warning("문장이 %d단어를 넘습니다: %s", rules.max_words_per_sentence, sentence)


def parse_and_validate(
    text: str,
    expected_series: str,
    rules: ContentRules,
    excluded_animals: Iterable[str] = (),
) -> Script:
    script = build_script(parse_json(text))
    validate_script(script, expected_series, rules, excluded_animals)
    return script
