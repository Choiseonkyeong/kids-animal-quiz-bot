"""표준 라이브러리(urllib)만 쓰는 JSON POST + 재시도 헬퍼."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **headers}
    last_error: HttpError | None = None
    for attempt in range(max_retries + 1):
        if attempt:
            delay = 2 ** attempt
            logger.info("재시도 %d/%d (%ds 대기)", attempt, max_retries, delay)
            time.sleep(delay)
        request = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            last_error = HttpError(f"HTTP {exc.code}: {detail}", exc.code)
            if exc.code not in _RETRYABLE_STATUS:
                raise last_error from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = HttpError(f"네트워크 오류: {exc}")
        except json.JSONDecodeError as exc:
            raise HttpError(f"응답 JSON 파싱 실패: {exc}") from exc
    assert last_error is not None
    raise last_error
