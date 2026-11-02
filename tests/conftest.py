from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_script_dict(series: str = "baby", n: int = 5, **overrides: Any) -> dict[str, Any]:
    pairs = [("소", "송아지"), ("개구리", "올챙이"), ("닭", "병아리"), ("말", "망아지"), ("개", "강아지"), ("양", "새끼 양")]
    data: dict[str, Any] = {
        "series": series,
        "title": "아기 이름은? 농장 아기들 편",
        "hook": "동글동글 동물원에 온 걸 환영해요!",
        "quizzes": [
            {
                "question": f"{a}의 아기는 뭐라고 부를까요?",
                "answer": b,
                "animal": a,
                "hint_visual": f"a smiling mother {a}",
            }
            for a, b in pairs[:n]
        ],
        "outro": "다음에 또 동글동글 동물원에서 만나요~",
    }
    data.update(overrides)
    return data


@pytest.fixture
def script_json() -> str:
    return json.dumps(make_script_dict(), ensure_ascii=False)
