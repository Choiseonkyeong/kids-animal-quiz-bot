"""이미지 준비. 우선순위: assets/images/{이름}.png → 캐시 → OpenAI gpt-image-1 생성."""
from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps

from config import ImageConfig
from quizbot.errors import ImageGenerationError
from quizbot.http import HttpError, post_json

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.openai.com/v1/images/generations"
_LOCAL_EXTS: tuple[str, ...] = (".png", ".webp", ".jpg", ".jpeg")


class ImageProvider(Protocol):
    def generate(self, prompt: str, out: Path) -> Path: ...


class OpenAIImageProvider:
    def __init__(self, cfg: ImageConfig) -> None:
        api_key = os.getenv(cfg.api_key_env, "").strip()
        if not api_key:
            raise ImageGenerationError(f"{cfg.api_key_env} 환경 변수가 설정되지 않았습니다.")
        self._cfg = cfg
        self._api_key = api_key

    def generate(self, prompt: str, out: Path) -> Path:
        payload = {
            "model": self._cfg.model,
            "prompt": prompt,
            "size": self._cfg.size,
            "quality": self._cfg.quality,
            "background": "transparent",
            "output_format": "png",
            "n": 1,
        }
        try:
            data = post_json(
                _ENDPOINT,
                payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._cfg.timeout_sec,
                max_retries=self._cfg.max_retries,
            )
            b64 = data["data"][0]["b64_json"]
            out.write_bytes(base64.b64decode(b64))
        except HttpError as exc:
            raise ImageGenerationError(f"이미지 생성 실패: {exc}") from exc
        except (KeyError, IndexError, TypeError, binascii.Error) as exc:
            raise ImageGenerationError(f"이미지 응답 형식 오류: {exc}") from exc
        return out


class ImageService:
    """이미지 공급자가 없거나 실패해도 None을 돌려 렌더링은 계속되게 한다."""

    def __init__(self, cfg: ImageConfig, provider: ImageProvider | None) -> None:
        self._cfg = cfg
        self._provider = provider
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    def _local(self, name: str) -> Path | None:
        for ext in _LOCAL_EXTS:
            path = self._cfg.local_dir / f"{name}{ext}"
            if path.exists():
                return path
        return None

    def build_prompt(self, subject: str) -> str:
        return (
            f"{subject}. Single subject, centered, full body, no text, no letters. "
            f"Style: {self._cfg.style_keywords}."
        )

    def get(self, subject: str, local_name: str | None = None) -> Path | None:
        if local_name and (local := self._local(local_name)):
            return local
        prompt = self.build_prompt(subject)
        cached = self._cfg.cache_dir / f"{hashlib.sha1(prompt.encode()).hexdigest()}.png"
        if cached.exists() and cached.stat().st_size > 0:
            return cached
        if self._provider is None:
            logger.warning("이미지 공급자가 없어 '%s' 이미지를 생략합니다.", subject)
            return None
        try:
            return self._provider.generate(prompt, cached)
        except (ImageGenerationError, OSError) as exc:
            logger.warning("'%s' 이미지 생성 실패, 생략합니다: %s", subject, exc)
            return None


def make_silhouette(src: Path, out: Path, color: tuple[int, int, int] = (40, 40, 60)) -> Path | None:
    """투명 배경 이미지를 단색 실루엣으로 바꾼다. 알파가 없으면 밝기로 마스크를 만든다."""
    try:
        with Image.open(src) as img:
            rgba = img.convert("RGBA")
    except OSError as exc:
        logger.warning("실루엣 원본을 열지 못했습니다: %s", exc)
        return None
    alpha = rgba.getchannel("A")
    if alpha.getextrema() == (255, 255):  # 불투명 이미지 → 흰 배경 가정
        alpha = ImageOps.invert(rgba.convert("L")).point(lambda v: 255 if v > 25 else 0)
    shadow = Image.new("RGBA", rgba.size, (*color, 255))
    shadow.putalpha(alpha)
    shadow.save(out)
    return out
