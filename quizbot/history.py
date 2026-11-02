"""시리즈별 사용 동물 기록 (data/history.json)."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

History = dict[str, list[str]]


def load_history(path: Path) -> History:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("history 파일을 읽지 못해 비어 있는 기록으로 시작합니다: %s", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("history 형식이 올바르지 않아 무시합니다.")
        return {}
    return {k: [str(a) for a in v] for k, v in data.items() if isinstance(v, list)}


def recent_animals(history: History, series: str, keep: int) -> list[str]:
    return history.get(series, [])[-keep:]


def add_animals(history: History, series: str, animals: Iterable[str], keep: int) -> History:
    new = list(animals)
    merged = [a for a in history.get(series, []) if a not in set(new)] + new
    return {**history, series: merged[-keep:]}


def save_history(path: Path, history: History) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
