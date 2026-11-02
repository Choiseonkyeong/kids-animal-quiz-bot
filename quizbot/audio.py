"""동물 소리·BGM·효과음 탐색 및 기본 효과음 생성."""
from __future__ import annotations

import logging
import random
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_AUDIO_EXTS: tuple[str, ...] = (".mp3", ".wav", ".ogg", ".m4a")
_SAMPLE_RATE = 44100


def find_animal_sound(sounds_dir: Path, animal: str) -> Path | None:
    path = sounds_dir / f"{animal}.mp3"
    return path if path.exists() else None


def available_sound_animals(sounds_dir: Path) -> list[str]:
    if not sounds_dir.is_dir():
        return []
    return sorted(p.stem for p in sounds_dir.glob("*.mp3"))


def pick_bgm(bgm_dir: Path, rng: random.Random | None = None) -> Path | None:
    if not bgm_dir.is_dir():
        return None
    files = sorted(p for p in bgm_dir.iterdir() if p.suffix.lower() in _AUDIO_EXTS)
    if not files:
        logger.info("assets/bgm/에 파일이 없어 BGM 없이 진행합니다.")
        return None
    return (rng or random).choice(files)


def find_sfx(sfx_dir: Path, name: str) -> Path | None:
    for ext in _AUDIO_EXTS:
        path = sfx_dir / f"{name}{ext}"
        if path.exists():
            return path
    return None


def _tone(freqs: list[float], dur: float) -> np.ndarray:
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    wave_ = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    envelope = np.exp(-5 * t / dur)
    return (wave_ * envelope * 0.8).astype(np.float32)


def _write_wav(samples: np.ndarray, out: Path) -> Path:
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return out


def ensure_default_sfx(cache_dir: Path) -> tuple[Path, Path]:
    """효과음 파일이 없을 때 쓸 기본 '띵'(카운트다운)과 '짠'(정답) 소리를 만든다."""
    tick = cache_dir / "default_tick.wav"
    chime = cache_dir / "default_chime.wav"
    if not tick.exists():
        _write_wav(_tone([880.0, 1320.0], 0.25), tick)
    if not chime.exists():
        notes = [_tone([f, f * 2], 0.18) for f in (523.25, 659.25, 783.99)]
        _write_wav(np.concatenate([*notes, _tone([1046.5, 1568.0], 0.5)]), chime)
    return tick, chime
