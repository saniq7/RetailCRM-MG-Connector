"""Выгрузка переписок: нормализация сообщений и запись в JSON/JSONL/Markdown."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .mg import MgClient


@dataclass
class Transcript:
    """Одна переписка: чат + его сообщения в хронологическом порядке."""

    chat: dict[str, Any]
    messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def chat_id(self) -> int | None:
        value = self.chat.get("id")
        return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None

    @property
    def title(self) -> str:
        customer = self.chat.get("customer") or {}
        name = (
            self.chat.get("name")
            or customer.get("name")
            or customer.get("username")
            or f"chat-{self.chat_id}"
        )
        return str(name)

    @property
    def channel(self) -> str:
        channel = self.chat.get("channel") or {}
        return str(channel.get("type") or channel.get("name") or "unknown")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "title": self.title,
            "channel": self.channel,
            "created_at": self.chat.get("created_at"),
            "last_activity": self.chat.get("last_activity"),
            "messages": [normalize_message(m) for m in self.messages],
            "raw_chat": self.chat,
        }


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    """Приводит сообщение MG к плоскому виду, удобному для чтения и анализа."""
    sender = message.get("from") or {}
    content = message.get("content")
    if content is None and isinstance(message.get("data"), dict):
        content = message["data"].get("text")
    return {
        "id": message.get("id"),
        "time": message.get("time") or message.get("created_at"),
        "type": message.get("type"),
        "scope": message.get("scope"),
        "direction": "in" if str(sender.get("type")) == "customer" else "out",
        "author": sender.get("name") or sender.get("username") or sender.get("type") or "system",
        "author_type": sender.get("type"),
        "text": content,
        "attachments": message.get("items") or message.get("attachments") or [],
    }


def fetch_transcripts(
    client: MgClient,
    *,
    limit: int | None = None,
    messages_per_chat: int | None = None,
    channel_id: int | None = None,
) -> Iterator[Transcript]:
    """Тянет чаты и их сообщения из MessageGateway."""
    filters: dict[str, Any] = {}
    if channel_id is not None:
        filters["channel_id"] = channel_id
    count = 0
    for chat in client.chats(**filters):
        transcript = Transcript(chat=chat)
        chat_id = transcript.chat_id
        if chat_id is not None:
            transcript.messages = list(
                client.chat_messages(chat_id, max_items=messages_per_chat)
            )
        yield transcript
        count += 1
        if limit is not None and count >= limit:
            return


def to_markdown(transcript: Transcript) -> str:
    """Рендерит переписку в читаемый Markdown."""
    lines = [
        f"# {transcript.title}",
        "",
        f"- **Чат:** `{transcript.chat_id}`",
        f"- **Канал:** {transcript.channel}",
        f"- **Создан:** {transcript.chat.get('created_at') or '—'}",
        f"- **Сообщений:** {len(transcript.messages)}",
        "",
        "---",
        "",
    ]
    for message in transcript.messages:
        item = normalize_message(message)
        marker = "🟢" if item["direction"] == "in" else "🔵"
        head = f"**{marker} {item['author']}** · {item['time'] or '—'}"
        lines.append(head)
        text = item["text"]
        if text:
            lines.extend(f"> {line}" for line in str(text).splitlines())
        else:
            lines.append(f"> _{item['type'] or 'без текста'}_")
        if item["attachments"]:
            lines.append(f"> 📎 вложений: {len(item['attachments'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_export(
    transcripts: Iterable[Transcript],
    out_dir: Path,
    *,
    fmt: str = "json",
) -> list[Path]:
    """Сохраняет переписки на диск. Форматы: ``json``, ``jsonl``, ``md``."""
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if fmt == "jsonl":
        path = out_dir / "transcripts.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for transcript in transcripts:
                fh.write(json.dumps(transcript.to_dict(), ensure_ascii=False) + "\n")
        return [path]

    for transcript in transcripts:
        stem = f"chat-{transcript.chat_id or 'unknown'}"
        if fmt == "md":
            path = out_dir / f"{stem}.md"
            path.write_text(to_markdown(transcript), encoding="utf-8")
        else:
            path = out_dir / f"{stem}.json"
            path.write_text(
                json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        written.append(path)
    return written
