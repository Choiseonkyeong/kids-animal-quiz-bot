"""외부 API 없이 가짜 대본·TTS·이미지로 전체 파이프라인(렌더링 포함)을 실행한다."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from moviepy import VideoFileClip
from PIL import Image, ImageDraw

from config import AppConfig, ImageConfig, PathConfig
from conftest import make_script_dict
from quizbot.images import ImageService
from quizbot.pipeline import Services, create_episode
from quizbot.series import get_series

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "assets" / "fonts" / "NanumSquareRoundEB.ttf"
SOUND_ANIMALS = ["소", "오리", "고양이", "강아지", "닭"]

pytestmark = pytest.mark.skipif(
    not FONT.exists() or shutil.which("ffmpeg") is None, reason="폰트 또는 ffmpeg 없음"
)


def _tone_mp3(out: Path, seconds: float, freq: int) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={seconds}", "-ac", "1", "-b:a", "64k", str(out)],
        check=True,
    )
    return out


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return json.dumps(self.payload, ensure_ascii=False)


class FakeTTS:
    """글자 수에 비례한 길이의 톤 mp3를 만든다 (실제 TTS 속도 근사)."""

    def __init__(self, cache: Path) -> None:
        self.cache = cache
        self.count = 0

    def synthesize(self, text: str) -> Path:
        self.count += 1
        seconds = round(min(4.0, 0.6 + len(text) * 0.11), 2)
        return _tone_mp3(self.cache / f"tts_{self.count}.mp3", seconds, 300 + self.count * 20)


class FakeImageProvider:
    def generate(self, prompt: str, out: Path) -> Path:
        img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((60, 60, 452, 452), fill=(255, 190, 120, 255), outline=(90, 60, 40, 255), width=12)
        draw.ellipse((170, 190, 220, 240), fill=(40, 40, 40, 255))
        draw.ellipse((292, 190, 342, 240), fill=(40, 40, 40, 255))
        img.save(out)
        return out


def _config(tmp: Path) -> AppConfig:
    assets = tmp / "assets"
    (assets / "sounds").mkdir(parents=True)
    (assets / "bgm").mkdir()
    for i, animal in enumerate(SOUND_ANIMALS):
        _tone_mp3(assets / "sounds" / f"{animal}.mp3", 2.0, 500 + i * 50)
    _tone_mp3(assets / "bgm" / "calm.mp3", 8.0, 220)
    base = AppConfig()
    return replace(
        base,
        paths=PathConfig(
            prompts_dir=base.paths.prompts_dir,
            assets_dir=assets,
            output_dir=tmp / "output",
            history_path=tmp / "data" / "history.json",
        ),
        image=replace(ImageConfig(), local_dir=assets / "images", cache_dir=assets / "cache" / "images"),
    )


def _sound_payload() -> dict:
    data = make_script_dict(series="sound", title="누구 소리일까? 농장 친구들 편")
    data["quizzes"] = [
        {"question": "음매~ 이 소리는 누구일까요?", "answer": "소", "animal": "소", "hint_visual": "a cow"},
        {"question": "꽥꽥! 누가 노래할까요?", "answer": "오리", "animal": "오리", "hint_visual": "a duck"},
        {"question": "야옹~ 누구 소리일까요?", "answer": "고양이", "animal": "고양이", "hint_visual": "a cat"},
        {"question": "히이잉! 이 소리는 누구예요?", "answer": "말", "animal": "말", "hint_visual": "a horse"},
        {"question": "꼬끼오! 아침이에요. 누구일까요?", "answer": "닭", "animal": "닭", "hint_visual": "a hen"},
    ]
    return data


@pytest.mark.parametrize("series_key", ["sound", "baby"])
def test_create_episode(tmp_path: Path, series_key: str, caplog: pytest.LogCaptureFixture) -> None:
    cfg = _config(tmp_path)
    (tmp_path / "tts").mkdir()
    payload = _sound_payload() if series_key == "sound" else make_script_dict()
    svc = Services(
        completion=FakeClient(payload),
        tts=FakeTTS(tmp_path / "tts"),
        images=ImageService(cfg.image, FakeImageProvider()),
    )
    result = create_episode(cfg, get_series(series_key), svc, today=date(2026, 11, 2))

    assert result.folder.name == "20261102_01"
    for path in (result.video, result.script_json, result.thumbnail):
        assert path.exists() and path.stat().st_size > 0
    with VideoFileClip(str(result.video)) as clip:
        assert tuple(clip.size) == (1080, 1920)
        assert 40.0 <= clip.duration <= 55.5
        assert clip.audio is not None
    saved = json.loads(result.script_json.read_text(encoding="utf-8"))
    history = json.loads(cfg.paths.history_path.read_text(encoding="utf-8"))
    assert history[series_key] == [q["animal"] for q in saved["quizzes"]]
    if series_key == "sound":  # 말.mp3가 없으므로 해당 퀴즈는 건너뜀
        assert "말" not in [q["animal"] for q in saved["quizzes"]]
        assert any("소리 파일 없음" in r.message for r in caplog.records)
    keep = Path("/tmp/claude-0/smoke") / series_key
    keep.mkdir(parents=True, exist_ok=True)
    for path in (result.video, result.thumbnail, result.script_json):
        shutil.copy(path, keep / path.name)
