#!/usr/bin/env python3
"""Выгрузка последних переписок в Markdown.

    python3 examples/export_transcripts.py [каталог]

Конфигурация берётся из ~/.retailcrm-mg/.env — сначала выполните
`retailcrm-mg bootstrap`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from retailcrm_mg import Config, MgClient
from retailcrm_mg.export import fetch_transcripts, write_export

CHATS = 25
MESSAGES_PER_CHAT = 500


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "./export")

    config = Config.load()
    client = MgClient(config.require_mg_api_base(), config.require_bot_token())

    transcripts = fetch_transcripts(
        client,
        limit=CHATS,
        messages_per_chat=MESSAGES_PER_CHAT,
    )
    written = write_export(transcripts, out_dir, fmt="md")

    print(f"Записано переписок: {len(written)} → {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
