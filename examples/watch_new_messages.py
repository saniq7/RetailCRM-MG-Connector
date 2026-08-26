#!/usr/bin/env python3
"""Опрос новых сообщений MessageGateway.

Курсор — идентификатор последнего обработанного сообщения — хранится в файле,
поэтому перезапуск не приводит к повторной обработке.

    python3 examples/watch_new_messages.py

Остановка — Ctrl+C.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from retailcrm_mg import Config, MgClient
from retailcrm_mg.export import normalize_message

STATE_FILE = Path.home() / ".retailcrm-mg" / "watch-state.json"
POLL_INTERVAL = 15  # секунд


def load_cursor() -> int | None:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("since_id")


def save_cursor(since_id: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"since_id": since_id}), encoding="utf-8")


def handle(message: dict) -> None:
    """Здесь место вашей логике: очередь, вебхук, запись в БД."""
    item = normalize_message(message)
    arrow = "→" if item["direction"] == "in" else "←"
    print(f"[{item['time']}] {arrow} {item['author']}: {item['text'] or item['type']}")


def main() -> int:
    config = Config.load()
    client = MgClient(config.require_mg_api_base(), config.require_bot_token())
    cursor = load_cursor()
    print(f"Слушаем {config.mg_api_base}, курсор: {cursor or 'с начала'}")

    while True:
        params = {"since_id": cursor} if cursor else {}
        latest = cursor
        for message in client.messages(**params):
            handle(message)
            latest = message.get("id", latest)
        if latest and latest != cursor:
            cursor = latest
            save_cursor(cursor)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nостановлено")
