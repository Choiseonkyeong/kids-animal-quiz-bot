"""한 편 생성 흐름: 대본 → 소리 필터 → TTS → 이미지 → 타임라인 → 렌더링 → 저장."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config import AppConfig
from quizbot import audio, history
from quizbot.errors import AssetMissingError
from quizbot.images import ImageService, make_silhouette
from quizbot.models import EpisodeAssets, Quiz, QuizAssets, Script
from quizbot.renderer import EpisodeRenderer, audio_duration
from quizbot.script_gen import CompletionClient, build_prompts, generate_script
from quizbot.series import SeriesInfo
from quizbot.timeline import EpisodeDurations, QuizDurations, build_timeline, fit_quiz_count
from quizbot.tts import TTSProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EpisodeResult:
    folder: Path
    video: Path
    script_json: Path
    thumbnail: Path
    script: Script


@dataclass
class Services:
    completion: CompletionClient
    tts: TTSProvider
    images: ImageService


def next_output_dir(base: Path, series: str, today: date) -> Path:
    series_dir = base / series
    series_dir.mkdir(parents=True, exist_ok=True)
    prefix = today.strftime("%Y%m%d")
    n = 1
    while (series_dir / f"{prefix}_{n:02d}").exists():
        n += 1
    folder = series_dir / f"{prefix}_{n:02d}"
    folder.mkdir()
    return folder


def filter_sound_quizzes(script: Script, sounds_dir: Path, min_quizzes: int) -> tuple[Script, dict[int, Path]]:
    """소리 파일이 없는 퀴즈는 건너뛴다. 남은 퀴즈 인덱스별 소리 경로를 함께 돌려준다."""
    kept: list[Quiz] = []
    sounds: dict[int, Path] = {}
    for quiz in script.quizzes:
        path = audio.find_animal_sound(sounds_dir, quiz.animal)
        if path is None:
            logger.warning("소리 파일 없음 → 퀴즈 건너뜀: %s", sounds_dir / f"{quiz.animal}.mp3")
            continue
        sounds[len(kept)] = path
        kept.append(quiz)
    if len(kept) < min_quizzes:
        raise AssetMissingError(f"소리 파일이 있는 퀴즈가 {len(kept)}개뿐입니다 (최소 {min_quizzes}개).")
    return script.with_quizzes(kept), sounds


def reveal_subject(series: SeriesInfo, quiz: Quiz) -> tuple[str, str | None]:
    """(이미지 프롬프트 주제, 로컬 파일 이름)."""
    if series.reveal_subject == "answer":
        return quiz.answer, quiz.answer
    if series.reveal_subject == "hint":
        return quiz.hint_visual, None
    return quiz.animal, quiz.animal


def prepare_quiz_images(
    series: SeriesInfo, quiz: Quiz, images: ImageService, work_dir: Path, index: int
) -> tuple[Path | None, Path | None]:
    subject, local = reveal_subject(series, quiz)
    reveal = images.get(subject, local)
    if series.question_visual == "silhouette":
        animal_img = reveal if series.reveal_subject == "animal" else images.get(quiz.animal, quiz.animal)
        question = make_silhouette(animal_img, work_dir / f"silhouette_{index}.png") if animal_img else None
    else:
        question = images.get(quiz.hint_visual)
    if series.reveal_subject == "hint":
        reveal = question
    return question, reveal


def prepare_assets(
    cfg: AppConfig, series: SeriesInfo, script: Script, sounds: dict[int, Path], svc: Services, work_dir: Path
) -> EpisodeAssets:
    assets_dir = cfg.paths.assets_dir
    tick, chime = audio.ensure_default_sfx(assets_dir / "cache" / "sfx")
    quizzes: list[QuizAssets] = []
    for i, quiz in enumerate(script.quizzes):
        q_img, r_img = prepare_quiz_images(series, quiz, svc.images, work_dir, i)
        quizzes.append(
            QuizAssets(
                quiz=quiz,
                question_image=q_img,
                reveal_image=r_img,
                question_tts=svc.tts.synthesize(quiz.question),
                reveal_tts=svc.tts.synthesize(f"정답은 {quiz.answer}!"),
                animal_sound=sounds.get(i),
            )
        )
    logo = assets_dir / "logo.png"
    return EpisodeAssets(
        script=script,
        hook_tts=svc.tts.synthesize(script.hook),
        outro_tts=svc.tts.synthesize(script.outro),
        quizzes=tuple(quizzes),
        bgm=audio.pick_bgm(assets_dir / "bgm"),
        logo=logo if logo.exists() else None,
        countdown_sfx=audio.find_sfx(assets_dir / "sfx", "countdown") or tick,
        reveal_sfx=audio.find_sfx(assets_dir / "sfx", "reveal") or chime,
    )


def measure(assets: EpisodeAssets) -> EpisodeDurations:
    return EpisodeDurations(
        hook_tts=audio_duration(assets.hook_tts),
        outro_tts=audio_duration(assets.outro_tts),
        quizzes=tuple(
            QuizDurations(
                question_tts=audio_duration(q.question_tts),
                reveal_tts=audio_duration(q.reveal_tts),
                animal_sound=audio_duration(q.animal_sound) if q.animal_sound else 0.0,
            )
            for q in assets.quizzes
        ),
    )


def trim_assets(assets: EpisodeAssets, n: int) -> EpisodeAssets:
    if n >= len(assets.quizzes):
        return assets
    logger.info("영상이 길어 퀴즈를 %d개로 줄입니다.", n)
    quizzes = assets.quizzes[:n]
    script = assets.script.with_quizzes([q.quiz for q in quizzes])
    return EpisodeAssets(
        script, assets.hook_tts, assets.outro_tts, quizzes,
        assets.bgm, assets.logo, assets.countdown_sfx, assets.reveal_sfx,
    )


def obtain_script(cfg: AppConfig, series: SeriesInfo, svc: Services) -> tuple[Script, dict[int, Path]]:
    hist = history.load_history(cfg.paths.history_path)
    excluded = history.recent_animals(hist, series.key, cfg.paths.history_keep)
    sounds_dir = cfg.paths.assets_dir / "sounds"
    allowed: list[str] | None = None
    if series.requires_animal_sound:
        allowed = [a for a in audio.available_sound_animals(sounds_dir) if a not in excluded]
        if len(allowed) < cfg.video.min_quizzes:
            raise AssetMissingError(
                f"사용 가능한 동물 소리 파일이 {len(allowed)}개뿐입니다. assets/sounds/에 더 추가하세요."
            )
    system, user = build_prompts(cfg.paths.prompts_dir, series.key, cfg.channel, cfg.rules, excluded, allowed)
    script = generate_script(
        svc.completion, system, user, series.key, cfg.rules, excluded, cfg.claude.max_regenerations
    )
    if series.requires_animal_sound:
        return filter_sound_quizzes(script, sounds_dir, cfg.video.min_quizzes)
    return script, {}


def create_episode(cfg: AppConfig, series: SeriesInfo, svc: Services, today: date | None = None) -> EpisodeResult:
    script, sounds = obtain_script(cfg, series, svc)
    folder = next_output_dir(cfg.paths.output_dir, series.key, today or date.today())
    work_dir = folder / "_work"
    work_dir.mkdir()
    assets = prepare_assets(cfg, series, script, sounds, svc, work_dir)
    durations = measure(assets)
    n = fit_quiz_count(durations, cfg.video)
    assets = trim_assets(assets, n)
    durations = EpisodeDurations(durations.hook_tts, durations.outro_tts, durations.quizzes[:n])
    segments = build_timeline(durations, cfg.video)

    renderer = EpisodeRenderer(cfg, series, assets)
    video = renderer.render(segments, folder / "video.mp4")
    thumbnail = renderer.render_thumbnail(folder / "thumbnail.png")
    script_json = folder / "script.json"
    script_json.write_text(json.dumps(assets.script.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    hist = history.load_history(cfg.paths.history_path)
    animals = [q.animal for q in assets.script.quizzes]
    history.save_history(
        cfg.paths.history_path, history.add_animals(hist, series.key, animals, cfg.paths.history_keep)
    )
    return EpisodeResult(folder, video, script_json, thumbnail, assets.script)
