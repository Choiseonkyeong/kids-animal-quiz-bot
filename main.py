"""동글동글 동물원 퀴즈 숏츠 생성기.

python main.py --series {sound,footprint,baby,count,food} [--count N] [--upload]
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from config import AppConfig, load_config
from quizbot.errors import ImageGenerationError, QuizBotError
from quizbot.images import ImageService, OpenAIImageProvider
from quizbot.pipeline import Services, create_episode
from quizbot.script_gen import ClaudeClient
from quizbot.series import SERIES, get_series
from quizbot.tts import GoogleTTS

logger = logging.getLogger("quizbot")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="동글동글 동물원 퀴즈 숏츠 생성기")
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--count", type=int, default=1, help="생성할 편 수 (기본 1)")
    parser.add_argument("--upload", action="store_true", help="지정 시 YouTube 업로드")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count는 1 이상이어야 합니다.")
    return args


def build_services(cfg: AppConfig) -> Services:
    try:
        provider: OpenAIImageProvider | None = OpenAIImageProvider(cfg.image)
    except ImageGenerationError as exc:
        logger.warning("%s → assets/images/ 로컬 이미지만 사용합니다.", exc)
        provider = None
    return Services(
        completion=ClaudeClient(cfg.claude),
        tts=GoogleTTS(cfg.tts),
        images=ImageService(cfg.image, provider),
    )


def run(args: argparse.Namespace) -> int:
    cfg = load_config()
    series = get_series(args.series)
    svc = build_services(cfg)
    for n in range(1, args.count + 1):
        logger.info("[%d/%d] '%s' 생성 시작", n, args.count, series.name)
        result = create_episode(cfg, series, svc)
        logger.info("생성 완료: %s", result.folder)
        if args.upload:
            from quizbot.uploader import upload_video  # 업로드할 때만 Google 라이브러리 로드

            upload_video(result.video, result.thumbnail, result.script, series, cfg.channel, cfg.upload)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv()
    try:
        return run(args)
    except QuizBotError as exc:
        logger.error("%s", exc)
        return 1
    except ValueError as exc:
        logger.error("설정 오류: %s", exc)
        return 2
    except KeyboardInterrupt:
        logger.error("사용자가 중단했습니다.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
