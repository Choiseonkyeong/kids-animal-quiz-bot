"""YouTube Data API v3 업로드. 첫 실행 때만 브라우저 OAuth 인증, 이후 token.json 재사용."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import ChannelConfig, UploadConfig
from quizbot.errors import UploadError
from quizbot.models import Script
from quizbot.series import SeriesInfo

logger = logging.getLogger(__name__)

_TITLE_MAX = 100
_RETRYABLE_STATUS = {500, 502, 503, 504}


def build_title(script: Script, channel: ChannelConfig) -> str:
    tags = " ".join(channel.hashtags)
    room = _TITLE_MAX - len(tags) - 1
    title = script.title if len(script.title) <= room else script.title[: max(0, room - 1)] + "…"
    return f"{title} {tags}".strip()


def build_description(series: SeriesInfo, channel: ChannelConfig) -> str:
    return f"{channel.intro}\n시리즈: {series.name}\n\n{' '.join(channel.hashtags)}"


def build_body(script: Script, series: SeriesInfo, channel: ChannelConfig, cfg: UploadConfig) -> dict[str, Any]:
    return {
        "snippet": {
            "title": build_title(script, channel),
            "description": build_description(series, channel),
            "tags": [t.lstrip("#") for t in channel.hashtags] + [series.name],
            "categoryId": cfg.category_id,
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": cfg.privacy_status,
            "selfDeclaredMadeForKids": True,
        },
    }


def load_credentials(cfg: UploadConfig) -> Credentials:
    creds: Credentials | None = None
    scopes = list(cfg.scopes)
    if cfg.token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(cfg.token_path), scopes)
        except (ValueError, OSError) as exc:
            logger.warning("token.json을 읽지 못해 다시 인증합니다: %s", exc)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except (RefreshError, TransportError) as exc:
            logger.warning("토큰 갱신 실패, 다시 인증합니다: %s", exc)
            creds = None
    if not creds or not creds.valid:
        if not cfg.client_secret_path.exists():
            raise UploadError(f"OAuth 클라이언트 파일이 없습니다: {cfg.client_secret_path}")
        flow = InstalledAppFlow.from_client_secrets_file(str(cfg.client_secret_path), scopes)
        creds = flow.run_local_server(port=0)
    cfg.token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _resumable_upload(request: Any, max_retries: int) -> dict[str, Any]:
    response: dict[str, Any] | None = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info("업로드 진행 %d%%", int(status.progress() * 100))
        except HttpError as exc:
            if exc.resp.status not in _RETRYABLE_STATUS or retries >= max_retries:
                raise UploadError(f"YouTube 업로드 실패: {exc}") from exc
            retries += 1
            time.sleep(2**retries)
        except (OSError, TransportError) as exc:
            if retries >= max_retries:
                raise UploadError(f"네트워크 오류로 업로드 실패: {exc}") from exc
            retries += 1
            time.sleep(2**retries)
    return response


def upload_video(
    video: Path,
    thumbnail: Path | None,
    script: Script,
    series: SeriesInfo,
    channel: ChannelConfig,
    cfg: UploadConfig,
) -> str:
    if not video.exists():
        raise UploadError(f"업로드할 영상이 없습니다: {video}")
    youtube = build("youtube", "v3", credentials=load_credentials(cfg), cache_discovery=False)
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body=build_body(script, series, channel, cfg), media_body=media
    )
    response = _resumable_upload(request, cfg.max_retries)
    video_id = response.get("id")
    if not video_id:
        raise UploadError(f"업로드 응답에 영상 ID가 없습니다: {response}")
    logger.info("업로드 완료: https://youtu.be/%s (%s)", video_id, cfg.privacy_status)
    if thumbnail and thumbnail.exists():
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
        except HttpError as exc:  # 인증되지 않은 채널은 썸네일 업로드 불가
            logger.warning("썸네일 업로드 실패 (영상은 업로드됨): %s", exc)
    return video_id
