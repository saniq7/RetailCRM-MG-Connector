"""Идемпотентная запись значений в ``.env`` (без дублей и потери комментариев)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .config import parse_env_text


def render_env(existing: str, updates: Mapping[str, str]) -> str:
    """Возвращает новое содержимое ``.env``.

    Существующие ключи обновляются на месте, новые дописываются в конец,
    комментарии и посторонние строки сохраняются.
    """
    lines = existing.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            if key in updates and key not in seen:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
            if key in seen:
                # Дубликат ранее обновлённого ключа — выкидываем.
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    return "\n".join(out).strip("\n") + "\n"


def update_env_file(path: Path, updates: Mapping[str, str]) -> Path:
    """Пишет значения в ``.env`` и выставляет права ``0600``."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(render_env(existing, updates), encoding="utf-8")
    path.chmod(0o600)
    return path


def read_env_file(path: Path) -> dict[str, str]:
    path = Path(path).expanduser()
    if not path.exists():
        return {}
    return parse_env_text(path.read_text(encoding="utf-8"))
