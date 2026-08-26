#!/usr/bin/env python3
"""Поиск подстроки по сообщениям всех чатов.

    python3 examples/search_messages.py "не пришёл заказ"
"""

from __future__ import annotations

import sys

from retailcrm_mg import Config, MgClient
from retailcrm_mg.export import normalize_message

MAX_CHATS = 100


def main() -> int:
    if len(sys.argv) < 2:
        print("укажите, что искать", file=sys.stderr)
        return 2
    needle = sys.argv[1].lower()

    config = Config.load()
    client = MgClient(config.require_mg_api_base(), config.require_bot_token())

    found = 0
    for index, chat in enumerate(client.chats()):
        if index >= MAX_CHATS:
            break
        customer = (chat.get("customer") or {}).get("name") or chat["id"]
        for message in client.chat_messages(chat["id"]):
            item = normalize_message(message)
            text = str(item["text"] or "")
            if needle in text.lower():
                found += 1
                print(f"чат {chat['id']} · {customer} · {item['time']}")
                print(f"    {item['author']}: {text}")

    print(f"\nНайдено совпадений: {found}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
