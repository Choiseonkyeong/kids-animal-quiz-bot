"""전역 설정. 값은 dataclass 기본값으로 관리하고, 일부는 환경 변수로 덮어쓴다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT_DIR = Path(__file__).resolve().parent

PrivacyStatus = Literal["private", "unlisted", "public"]


@dataclass(frozen=True)
class ChannelConfig:
    name: str = "동글동글 동물원"
    intro: str = "동글동글 동물원은 4~7세 친구들과 함께하는 귀여운 동물 퀴즈 채널이에요!"
    hashtags: tuple[str, ...] = ("#동글동글동물원", "#동물퀴즈", "#유아", "#shorts")


@dataclass(frozen=True)
class ClaudeConfig:
    model: str = "claude-opus-5-5"
    max_tokens: int = 8000
    effort: Literal["low", "medium", "high"] = "low"
    max_regenerations: int = 2  # 최초 1회 + 재생성 최대 2회
    use_refusal_fallbacks: bool = True
    timeout_sec: float = 120.0


@dataclass(frozen=True)
class TTSConfig:
    api_key_env: str = "GOOGLE_TTS_API_KEY"
    language_code: str = "ko-KR"
    voice_name: str = "ko-KR-Neural2-A"  # 밝은 여성 톤
    speaking_rate: float = 0.85
    pitch: float = 2.0  # 반음 단위, 약간 높여 밝게
    timeout_sec: float = 30.0
    max_retries: int = 3
    cache_dir: Path = ROOT_DIR / "assets" / "cache" / "tts"


@dataclass(frozen=True)
class ImageConfig:
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-image-1"
    size: str = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"
    style_keywords: str = "cute, cartoon, rounded, bright pastel, child-friendly"
    timeout_sec: float = 180.0
    max_retries: int = 2
    local_dir: Path = ROOT_DIR / "assets" / "images"  # 수동 준비 이미지가 있으면 우선 사용
    cache_dir: Path = ROOT_DIR / "assets" / "cache" / "images"


@dataclass(frozen=True)
class FontConfig:
    path: Path = ROOT_DIR / "assets" / "fonts" / "NanumSquareRoundEB.ttf"
    title_size: int = 130
    keyword_size: int = 150
    answer_size: int = 210
    countdown_size: int = 560
    fill: str = "#FFFFFF"
    stroke: str = "#333333"
    stroke_width: int = 16


@dataclass(frozen=True)
class StyleConfig:
    palette: tuple[str, ...] = ("#FFD93D", "#6BCB77", "#4D96FF", "#FF6B6B")


@dataclass(frozen=True)
class VideoConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    hook_sec: float = 3.0
    countdown_sec: float = 3.0
    reveal_min_sec: float = 2.5
    outro_min_sec: float = 3.0
    outro_max_sec: float = 5.0
    min_total_sec: float = 40.0
    max_total_sec: float = 55.0
    animal_sound_max_sec: float = 4.0
    narration_lead_sec: float = 0.2
    reveal_narration_delay_sec: float = 0.6  # 정답 효과음 뒤 나레이션 시작
    bgm_volume: float = 0.12
    sfx_volume: float = 0.6
    animal_sound_volume: float = 1.0
    logo_width: int = 170
    min_quizzes: int = 3


@dataclass(frozen=True)
class UploadConfig:
    privacy_status: PrivacyStatus = "private"
    category_id: str = "15"  # Pets & Animals
    client_secret_path: Path = ROOT_DIR / "client_secret.json"
    token_path: Path = ROOT_DIR / "token.json"
    scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/youtube.upload",)
    max_retries: int = 5


@dataclass(frozen=True)
class PathConfig:
    prompts_dir: Path = ROOT_DIR / "prompts"
    assets_dir: Path = ROOT_DIR / "assets"
    output_dir: Path = ROOT_DIR / "output"
    history_path: Path = ROOT_DIR / "data" / "history.json"
    history_keep: int = 40  # 시리즈별로 최근 N마리를 제외 목록으로 사용


@dataclass(frozen=True)
class ContentRules:
    # 문자열은 정규식. "피"는 "피자/커피" 오탐을 막기 위해 단어 경계를 둔다.
    forbidden_patterns: tuple[str, ...] = (
        r"사냥", r"죽음", r"죽었", r"죽어", r"죽이", r"죽는", r"멸종",
        r"(?<![가-힣])피(?:가|를|는|도|이)?(?![가-힣])", r"잡아먹", r"먹잇감",
        r"무서", r"슬퍼", r"슬픈", r"다치", r"상처", r"괴물",
        r"(?i)\b(?:hunt\w*|kill\w*|dead|death|blood\w*|extinct\w*|prey|scary)\b",
    )
    max_words_per_sentence: int = 10
    min_quizzes: int = 3  # 검증 허용 범위
    max_quizzes: int = 6
    prompt_min_quizzes: int = 4  # 프롬프트 요청 범위
    prompt_max_quizzes: int = 5


@dataclass(frozen=True)
class AppConfig:
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    font: FontConfig = field(default_factory=FontConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    rules: ContentRules = field(default_factory=ContentRules)


_VALID_PRIVACY: tuple[PrivacyStatus, ...] = ("private", "unlisted", "public")


def load_config() -> AppConfig:
    """기본 설정에 환경 변수 덮어쓰기를 적용한다 (.env는 main에서 미리 로드)."""
    privacy = os.getenv("YOUTUBE_PRIVACY_STATUS", "private").strip().lower()
    if privacy not in _VALID_PRIVACY:
        raise ValueError(f"YOUTUBE_PRIVACY_STATUS는 {_VALID_PRIVACY} 중 하나여야 합니다: {privacy!r}")
    claude_model = os.getenv("CLAUDE_MODEL", "").strip()
    return AppConfig(
        claude=ClaudeConfig(model=claude_model) if claude_model else ClaudeConfig(),
        upload=UploadConfig(privacy_status=privacy),  # type: ignore[arg-type]
    )
