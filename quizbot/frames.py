"""Pillow로 구간별 정지 화면(배경+큰 글자)과 움직일 이미지(스프라이트)를 만든다."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont

from config import FontConfig, VideoConfig
from quizbot.errors import AssetMissingError

logger = logging.getLogger(__name__)

_DECOR_COLORS: tuple[str, ...] = ("#FFFFFF", "#FFF6C7", "#FFE0EC", "#E3F6FF")


@dataclass(frozen=True)
class FrameSpec:
    base: Image.Image  # RGB 전체 화면
    sprite: Image.Image | None = None  # RGBA, 위아래로 통통 튀게 렌더링
    sprite_center: tuple[int, int] = (0, 0)


class FramePainter:
    def __init__(self, font: FontConfig, video: VideoConfig, logo: Path | None) -> None:
        if not font.path.exists():
            raise AssetMissingError(f"폰트 파일이 없습니다: {font.path} (README의 폰트 준비 참고)")
        self._font_cfg = font
        self._video = video
        self._size = (video.width, video.height)
        self._logo = self._load_logo(logo)
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}

    # ---------- 공통 도구 ----------
    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._font_cache:
            self._font_cache[size] = ImageFont.truetype(str(self._font_cfg.path), size)
        return self._font_cache[size]

    def _load_logo(self, path: Path | None) -> Image.Image | None:
        if path is None or not path.exists():
            return None
        try:
            with Image.open(path) as img:
                logo = img.convert("RGBA")
        except OSError as exc:
            logger.warning("로고를 열지 못해 생략합니다: %s", exc)
            return None
        ratio = self._video.logo_width / logo.width
        return logo.resize((self._video.logo_width, max(1, int(logo.height * ratio))), Image.LANCZOS)

    def background(self, color: str, seed: int) -> Image.Image:
        img = Image.new("RGB", self._size, color)
        draw = ImageDraw.Draw(img, "RGBA")
        rng = random.Random(seed)
        for _ in range(14):  # 동글동글 물방울 장식
            r = rng.randint(30, 110)
            x, y = rng.randint(0, self._size[0]), rng.randint(0, self._size[1])
            fill = ImageColor.getrgb(rng.choice(_DECOR_COLORS))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(*fill, 70))
        return img

    def draw_text(
        self, img: Image.Image, text: str, size: int, center_y: int, fill: str | None = None
    ) -> None:
        draw = ImageDraw.Draw(img)
        max_width = self._size[0] - 120
        stroke = self._font_cfg.stroke_width
        while size > 40:
            font = self._font(size)
            left, _, right, _ = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
            if right - left <= max_width:
                break
            size = int(size * 0.9)
        draw.text(
            (self._size[0] // 2, center_y),
            text,
            font=self._font(size),
            fill=fill or self._font_cfg.fill,
            stroke_width=max(4, int(stroke * size / self._font_cfg.answer_size)),
            stroke_fill=self._font_cfg.stroke,
            anchor="mm",
        )

    def paste_logo(self, img: Image.Image) -> None:
        if self._logo is not None:
            img.paste(self._logo, (40, 40), self._logo)

    @staticmethod
    def load_sprite(path: Path | None, max_side: int) -> Image.Image | None:
        if path is None:
            return None
        try:
            with Image.open(path) as src:
                sprite = src.convert("RGBA")
        except OSError as exc:
            logger.warning("이미지를 열지 못해 생략합니다 (%s): %s", path, exc)
            return None
        bbox = sprite.getchannel("A").getbbox()  # 투명 여백 제거
        if bbox:
            sprite = sprite.crop(bbox)
        scale = max_side / max(sprite.size)
        return sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))), Image.LANCZOS)

    def _with_sprite(self, base: Image.Image, sprite: Image.Image | None, center: tuple[int, int]) -> FrameSpec:
        self.paste_logo(base)
        return FrameSpec(base, sprite, center)

    # ---------- 구간별 화면 ----------
    def hook(self, channel_name: str, series_name: str, color: str) -> FrameSpec:
        img = self.background(color, seed=1)
        self.draw_text(img, channel_name, self._font_cfg.title_size, 700)
        self.draw_text(img, series_name, self._font_cfg.keyword_size, 940, fill="#FFF3A0")
        self.draw_text(img, "?", 420, 1380)
        return self._with_sprite(img, None, (0, 0))

    def question(self, number: int, caption: str, image: Path | None, color: str) -> FrameSpec:
        img = self.background(color, seed=10 + number)
        self.draw_text(img, f"{number}번", 110, 200, fill="#FFF3A0")
        self.draw_text(img, caption, self._font_cfg.keyword_size, 380)
        sprite = self.load_sprite(image, 860)
        if sprite is None:
            self.draw_text(img, "?", 520, 1100)
        return self._with_sprite(img, sprite, (540, 1080))

    def countdown(self, question: FrameSpec, number: int) -> Image.Image:
        img = question.base.copy()
        if question.sprite is not None:
            cx, cy = question.sprite_center
            w, h = question.sprite.size
            img.paste(question.sprite, (cx - w // 2, cy - h // 2), question.sprite)
        img = ImageEnhance.Brightness(img).enhance(0.75)
        self.draw_text(img, str(number), self._font_cfg.countdown_size, self._size[1] // 2, fill="#FFF3A0")
        return img

    def reveal(self, answer: str, image: Path | None, color: str, number: int) -> FrameSpec:
        img = self.background(color, seed=100 + number)
        self.draw_text(img, "딩동댕!", 110, 200, fill="#FFF3A0")
        self.draw_text(img, answer, self._font_cfg.answer_size, 1300)
        return self._with_sprite(img, self.load_sprite(image, 760), (540, 720))

    def outro(self, channel_name: str, color: str) -> FrameSpec:
        img = self.background(color, seed=999)
        self.draw_text(img, channel_name, self._font_cfg.title_size, 820)
        self.draw_text(img, "또 만나요~", self._font_cfg.keyword_size, 1080, fill="#FFF3A0")
        return self._with_sprite(img, None, (0, 0))

    def thumbnail(self, series_name: str, channel_name: str, image: Path | None, color: str) -> Image.Image:
        img = self.background(color, seed=7)
        self.draw_text(img, series_name, self._font_cfg.answer_size, 330)
        sprite = self.load_sprite(image, 900)
        if sprite is not None:
            w, h = sprite.size
            img.paste(sprite, (540 - w // 2, 1050 - h // 2), sprite)
        else:
            self.draw_text(img, "?", 600, 1050)
        self.draw_text(img, channel_name, self._font_cfg.keyword_size, 1700, fill="#FFF3A0")
        self.paste_logo(img)
        return img
