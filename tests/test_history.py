from __future__ import annotations

from pathlib import Path

from quizbot.history import add_animals, load_history, recent_animals, save_history


def test_roundtrip_and_keep(tmp_path: Path) -> None:
    path = tmp_path / "h.json"
    assert load_history(path) == {}
    h = add_animals({}, "sound", ["소", "닭"], keep=3)
    h = add_animals(h, "sound", ["오리", "소"], keep=3)
    save_history(path, h)
    loaded = load_history(path)
    assert recent_animals(loaded, "sound", 3) == ["닭", "오리", "소"]
    assert recent_animals(loaded, "baby", 3) == []


def test_corrupt_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "h.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_history(path) == {}
