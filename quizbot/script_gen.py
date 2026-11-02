"""Claude API로 대본을 생성하고 검증·재생성한다."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from string import Template
from typing import Any, Protocol

import anthropic

from config import ChannelConfig, ClaudeConfig, ContentRules
from quizbot.errors import ScriptGenerationError, ScriptValidationError
from quizbot.models import Script
from quizbot.validator import parse_and_validate

logger = logging.getLogger(__name__)

_QUIZ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("question", "answer", "animal", "hint_visual")},
    "required": ["question", "answer", "animal", "hint_visual"],
    "additionalProperties": False,
}
SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "series": {"type": "string"},
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "quizzes": {"type": "array", "items": _QUIZ_SCHEMA},
        "outro": {"type": "string"},
    },
    "required": ["series", "title", "hook", "quizzes", "outro"],
    "additionalProperties": False,
}


class CompletionClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class ClaudeClient:
    """anthropic SDK 래퍼. 네트워크·429·5xx 재시도는 SDK(max_retries)가 처리한다."""

    def __init__(self, cfg: ClaudeConfig) -> None:
        self._cfg = cfg
        self._client = anthropic.Anthropic(timeout=cfg.timeout_sec, max_retries=3)

    def _request_kwargs(self, system: str, user: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._cfg.model,
            "max_tokens": self._cfg.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": self._cfg.effort,
                "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA},
            },
        }
        if self._cfg.use_refusal_fallbacks:
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        return kwargs

    def complete(self, system: str, user: str) -> str:
        kwargs = self._request_kwargs(system, user)
        try:
            if self._cfg.use_refusal_fallbacks:
                response = self._client.beta.messages.create(**kwargs)
            else:
                response = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ScriptGenerationError("Anthropic 인증 실패: ANTHROPIC_API_KEY를 확인하세요.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ScriptGenerationError("Anthropic API 권한이 없습니다.") from exc
        except anthropic.NotFoundError as exc:
            raise ScriptGenerationError(f"모델을 찾을 수 없습니다: {self._cfg.model}") from exc
        except anthropic.BadRequestError as exc:
            raise ScriptGenerationError(f"잘못된 요청: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise ScriptGenerationError("요청 한도 초과(429). 잠시 후 다시 실행하세요.") from exc
        except anthropic.APIStatusError as exc:
            raise ScriptGenerationError(f"Anthropic API 오류 ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise ScriptGenerationError("네트워크 오류로 Anthropic API에 연결하지 못했습니다.") from exc
        except TypeError as exc:  # SDK가 인증 정보를 찾지 못한 경우
            raise ScriptGenerationError(f"Anthropic 인증 정보가 없습니다. ANTHROPIC_API_KEY를 설정하세요. ({exc})") from exc

        if response.stop_reason == "refusal":
            raise ScriptValidationError("모델이 요청을 거절했습니다 (refusal).")
        if response.stop_reason == "max_tokens":
            raise ScriptValidationError("응답이 max_tokens에서 잘렸습니다.")
        text = "".join(b.text for b in response.content if b.type == "text")
        if not text.strip():
            raise ScriptValidationError("응답에 텍스트가 없습니다.")
        return text


def _read_prompt(path: Path) -> Template:
    try:
        return Template(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScriptGenerationError(f"프롬프트 파일이 없습니다: {path}") from exc


def build_prompts(
    prompts_dir: Path,
    series: str,
    channel: ChannelConfig,
    rules: ContentRules,
    excluded: Sequence[str],
    allowed_animals: Sequence[str] | None = None,
) -> tuple[str, str]:
    system = _read_prompt(prompts_dir / "system.md").safe_substitute(
        channel_name=channel.name,
        min_quizzes=rules.prompt_min_quizzes,
        max_quizzes=rules.prompt_max_quizzes,
    )
    user = _read_prompt(prompts_dir / "series" / f"{series}.md").safe_substitute(
        exclude=", ".join(excluded) if excluded else "없음",
    )
    if allowed_animals is not None:
        user += f"\n반드시 이 동물들 중에서만 고른다: {', '.join(allowed_animals)}\n"
    return system, user


def generate_script(
    client: CompletionClient,
    system: str,
    user: str,
    series: str,
    rules: ContentRules,
    excluded: Sequence[str],
    max_regenerations: int,
) -> Script:
    """최초 1회 + 최대 max_regenerations회 재생성. 모두 실패하면 ScriptGenerationError."""
    errors: list[str] = []
    for attempt in range(1, max_regenerations + 2):
        prompt = user
        if errors:
            prompt += f"\n\n[이전 답변 문제: {errors[-1]}] 이 문제를 고쳐서 다시 써 줘."
        try:
            text = client.complete(system, prompt)
            script = parse_and_validate(text, series, rules, excluded)
        except ScriptValidationError as exc:
            errors.append(str(exc))
            logger.warning("대본 검증 실패 (%d회차): %s", attempt, exc)
            continue
        logger.info("대본 생성 성공 (%d회차): %s", attempt, script.title)
        return script
    raise ScriptGenerationError(f"{max_regenerations}회 재생성 후에도 실패: {errors}")
