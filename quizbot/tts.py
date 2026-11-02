"""TTS. Google Cloud Text-to-Speech REST API (API 키 방식)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Protocol

from config import TTSConfig
from quizbot.errors import TTSError
from quizbot.http import HttpError, post_json

logger = logging.getLogger(__name__)

_ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> Path:
        """text를 음성 파일(mp3)로 만들고 경로를 돌려준다."""
        ...


class GoogleTTS:
    def __init__(self, cfg: TTSConfig) -> None:
        api_key = os.getenv(cfg.api_key_env, "").strip()
        if not api_key:
            raise TTSError(f"{cfg.api_key_env} 환경 변수가 설정되지 않았습니다.")
        self._cfg = cfg
        self._api_key = api_key
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, text: str) -> Path:
        key = json.dumps(
            [text, self._cfg.voice_name, self._cfg.speaking_rate, self._cfg.pitch], ensure_ascii=False
        )
        return self._cfg.cache_dir / f"{hashlib.sha1(key.encode()).hexdigest()}.mp3"

    def synthesize(self, text: str) -> Path:
        if not text.strip():
            raise TTSError("빈 문장은 음성으로 만들 수 없습니다.")
        out = self._cache_path(text)
        if out.exists() and out.stat().st_size > 0:
            return out
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": self._cfg.language_code, "name": self._cfg.voice_name},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": self._cfg.speaking_rate,
                "pitch": self._cfg.pitch,
            },
        }
        try:
            data = post_json(
                _ENDPOINT,
                payload,
                headers={"X-Goog-Api-Key": self._api_key},
                timeout=self._cfg.timeout_sec,
                max_retries=self._cfg.max_retries,
            )
        except HttpError as exc:
            raise TTSError(f"Google TTS 실패: {exc}") from exc
        content = data.get("audioContent")
        if not isinstance(content, str) or not content:
            raise TTSError("Google TTS 응답에 audioContent가 없습니다.")
        try:
            out.write_bytes(base64.b64decode(content))
        except (binascii.Error, OSError) as exc:
            raise TTSError(f"음성 파일 저장 실패: {exc}") from exc
        logger.debug("TTS 생성: %s", text)
        return out
