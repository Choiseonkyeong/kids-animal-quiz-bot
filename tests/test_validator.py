from __future__ import annotations

import json

import pytest

from config import ContentRules
from conftest import make_script_dict
from quizbot.errors import ScriptValidationError
from quizbot.validator import parse_and_validate

RULES = ContentRules()


def _dump(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False)


def test_valid_script_passes(script_json: str) -> None:
    script = parse_and_validate(script_json, "baby", RULES)
    assert len(script.quizzes) == 5
    assert script.quizzes[0].answer == "송아지"


def test_code_fence_is_stripped(script_json: str) -> None:
    assert parse_and_validate(f"```json\n{script_json}\n```", "baby", RULES).series == "baby"


def test_invalid_json_raises() -> None:
    with pytest.raises(ScriptValidationError, match="JSON 파싱 실패"):
        parse_and_validate("{not json", "baby", RULES)


def test_too_few_quizzes() -> None:
    with pytest.raises(ScriptValidationError, match="퀴즈 개수"):
        parse_and_validate(_dump(make_script_dict(n=2)), "baby", RULES)


def test_too_many_quizzes() -> None:
    data = make_script_dict(n=6)
    data["quizzes"].append(dict(data["quizzes"][0], animal="염소"))
    with pytest.raises(ScriptValidationError, match="퀴즈 개수"):
        parse_and_validate(_dump(data), "baby", RULES)


@pytest.mark.parametrize(
    "text",
    ["사자가 사냥을 해요", "공룡은 멸종했어요", "피가 나요", "토끼를 잡아먹어요", "무서운 늑대"],
)
def test_forbidden_words_detected(text: str) -> None:
    data = make_script_dict()
    data["quizzes"][1]["question"] = text
    with pytest.raises(ScriptValidationError, match="금지어"):
        parse_and_validate(_dump(data), "baby", RULES)


def test_forbidden_word_in_english_hint() -> None:
    data = make_script_dict()
    data["quizzes"][0]["hint_visual"] = "a lion hunting a zebra"
    with pytest.raises(ScriptValidationError, match="금지어"):
        parse_and_validate(_dump(data), "baby", RULES)


@pytest.mark.parametrize("text", ["피자를 좋아해요", "커피 색 강아지", "피곤한 곰"])
def test_similar_words_not_flagged(text: str) -> None:
    data = make_script_dict()
    data["quizzes"][0]["question"] = text
    parse_and_validate(_dump(data), "baby", RULES)


def test_missing_key_and_wrong_series(script_json: str) -> None:
    data = make_script_dict()
    del data["outro"]
    with pytest.raises(ScriptValidationError, match="필수 키"):
        parse_and_validate(_dump(data), "baby", RULES)
    with pytest.raises(ScriptValidationError, match="series"):
        parse_and_validate(script_json, "sound", RULES)


def test_excluded_and_duplicate_animals(script_json: str) -> None:
    with pytest.raises(ScriptValidationError, match="제외 목록"):
        parse_and_validate(script_json, "baby", RULES, excluded_animals=["소"])
    data = make_script_dict()
    data["quizzes"][1]["animal"] = "소"
    with pytest.raises(ScriptValidationError, match="중복"):
        parse_and_validate(_dump(data), "baby", RULES)
