from __future__ import annotations

import json

import pytest

from config import ChannelConfig, ContentRules, PathConfig
from conftest import make_script_dict
from quizbot.errors import ScriptGenerationError, ScriptValidationError
from quizbot.script_gen import build_prompts, generate_script

RULES = ContentRules()


class FakeClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        item = self.responses[len(self.prompts) - 1]
        if isinstance(item, Exception):
            raise item
        return item


def _forbidden() -> str:
    data = make_script_dict()
    data["quizzes"][0]["question"] = "사자가 사냥을 해요"
    return json.dumps(data, ensure_ascii=False)


def _valid() -> str:
    return json.dumps(make_script_dict(), ensure_ascii=False)


def test_regenerates_after_forbidden_word_and_bad_json() -> None:
    client = FakeClient([_forbidden(), "not json", _valid()])
    script = generate_script(client, "sys", "user", "baby", RULES, [], max_regenerations=2)
    assert script.title
    assert len(client.prompts) == 3
    assert "금지어" in client.prompts[1]  # 이전 실패 사유를 다음 요청에 전달
    assert "JSON" in client.prompts[2]


def test_fails_after_max_regenerations() -> None:
    client = FakeClient([_forbidden(), _forbidden(), _forbidden(), _valid()])
    with pytest.raises(ScriptGenerationError):
        generate_script(client, "sys", "user", "baby", RULES, [], max_regenerations=2)
    assert len(client.prompts) == 3  # 최초 1회 + 재생성 2회


def test_refusal_counts_as_failed_attempt() -> None:
    client = FakeClient([ScriptValidationError("refusal"), _valid()])
    generate_script(client, "sys", "user", "baby", RULES, [], max_regenerations=2)
    assert len(client.prompts) == 2


def test_api_error_is_not_retried() -> None:
    client = FakeClient([ScriptGenerationError("auth"), _valid()])
    with pytest.raises(ScriptGenerationError):
        generate_script(client, "sys", "user", "baby", RULES, [], max_regenerations=2)
    assert len(client.prompts) == 1


@pytest.mark.parametrize("series", ["sound", "footprint", "baby", "count", "food"])
def test_prompts_render(series: str) -> None:
    system, user = build_prompts(PathConfig().prompts_dir, series, ChannelConfig(), RULES, ["소", "닭"], ["오리"])
    assert "동글동글 동물원" in system and "$" not in system
    assert "소, 닭" in user and "오리" in user and "$" not in user
