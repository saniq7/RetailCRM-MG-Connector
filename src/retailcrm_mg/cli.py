"""Командная строка коннектора: ``retailcrm-mg``."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config, mask, normalize_base_url, normalize_code, normalize_mg_api_base
from .envfile import update_env_file
from .errors import ConfigError, ConnectorError, TokenNotIssuedError
from .export import fetch_transcripts, write_export
from .http import HttpClient
from .mg import MgClient, take
from .retailcrm import RetailCrmClient, find_token_candidates

logger = logging.getLogger("retailcrm_mg")

OK = "✅"
FAIL = "❌"
WARN = "⚠️"


# --------------------------------------------------------------------------
# вспомогательное
# --------------------------------------------------------------------------


def _config(args: argparse.Namespace) -> Config:
    config = Config.load(env_file=getattr(args, "env_file", None))
    if getattr(args, "base_url", None):
        config.base_url = normalize_base_url(args.base_url)
    if getattr(args, "mg_api_base", None):
        config.mg_api_base = normalize_mg_api_base(args.mg_api_base)
    if getattr(args, "api_key", None):
        config.api_key = args.api_key
    if getattr(args, "module_code", None):
        config.module_code = normalize_code(args.module_code)
    if getattr(args, "module_name", None):
        config.module_name = args.module_name
    if getattr(args, "client_id", None):
        config.client_id = args.client_id
    return config


def _resolve_api_key(config: Config, args: argparse.Namespace) -> str:
    """Берёт ключ из аргументов/окружения/.env, иначе спрашивает без эха."""
    if config.api_key:
        return config.api_key
    if getattr(args, "ask_key", False) or sys.stdin.isatty():
        key = getpass.getpass(f"RetailCRM API key для {config.base_url}: ").strip()
        if key:
            config.api_key = key
            return key
    return config.require_api_key()


def _dump(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _rows(items: Sequence[dict[str, Any]], columns: Sequence[tuple[str, str]]) -> None:
    """Печатает простую выровненную таблицу без внешних библиотек."""
    if not items:
        print("(пусто)")
        return
    headers = [title for title, _ in columns]
    table = [[_cell(item, key) for _, key in columns] for item in items]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in table)) for i in range(len(columns))
    ]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * widths[i] for i in range(len(columns))))
    for row in table:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(columns))))


def _cell(item: dict[str, Any], dotted: str) -> str:
    node: Any = item
    for key in dotted.split("."):
        if not isinstance(node, dict):
            node = None
            break
        node = node.get(key)
    if node is None:
        return "—"
    text = str(node)
    return text if len(text) <= 48 else text[:45] + "..."


def _mg(config: Config) -> MgClient:
    return MgClient(
        config.require_mg_api_base(),
        config.require_bot_token(),
        http=HttpClient(timeout=config.timeout),
    )


def _crm(config: Config, api_key: str) -> RetailCrmClient:
    return RetailCrmClient(
        config.require_base_url(), api_key, http=HttpClient(timeout=config.timeout)
    )


# --------------------------------------------------------------------------
# команды
# --------------------------------------------------------------------------


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Регистрирует integration module и получает свежий mgBot-токен."""
    config = _config(args)
    config.require_base_url()
    api_key = _resolve_api_key(config, args)
    crm = _crm(config, api_key)

    print(f"{OK} RetailCRM: {config.base_url}")
    crm.ping()
    print(f"{OK} API-ключ принят ({mask(api_key)})")

    missing = crm.missing_credentials(config.module_code)
    if missing:
        print(f"{WARN} у ключа может не хватать прав: {', '.join(missing)}")

    existing = crm.get_module(config.module_code)
    if existing and not args.force:
        integrations = (existing.get("integrations") or {}).get("mgBot") or {}
        if integrations and not args.refresh:
            print(
                f"{WARN} модуль `{config.module_code}` уже существует и привязан к MG.\n"
                "    Повторный выпуск токена отзовёт старый. Используйте --refresh, "
                "чтобы всё равно перевыпустить, или --module-code для отдельного модуля."
            )
            return 2

    try:
        result = crm.bootstrap_mg_bot(
            code=config.module_code,
            name=config.module_name,
            client_id=config.client_id,
            refresh_token=True,
        )
    except TokenNotIssuedError as exc:
        print(f"{FAIL} {exc}")
        if args.dump_response:
            _dump({"hint": "полный ответ RetailCRM ниже"})
        return 1

    action = "создан" if result.created else "обновлён"
    print(f"{OK} integration module {action}: {result.module_code}")
    print(f"{OK} mgBot-токен выпущен: {mask(result.token)}")

    # Адрес MG свой у каждого аккаунта: берём указанный, иначе — из ответа RetailCRM.
    if not config.mg_api_base and result.mg_api_base:
        config.mg_api_base = normalize_mg_api_base(result.mg_api_base)
        print(f"{OK} адрес MessageGateway определён автоматически: {config.mg_api_base}")

    if args.dump_response:
        candidates = [(path, mask(value)) for path, value in find_token_candidates(result.raw)]
        _dump({"token_candidates": candidates, "response_keys": sorted(result.raw)})

    if args.no_write:
        print(f"{WARN} --no-write: токен не сохранён, задайте RETAILCRM_MG_BOT_TOKEN вручную")
        return 0

    updates = {
        "RETAILCRM_BASE_URL": config.base_url,
        "RETAILCRM_MG_MODULE_CODE": result.module_code,
        "RETAILCRM_MG_MODULE_NAME": result.module_name,
        "RETAILCRM_MG_CLIENT_ID": result.client_id,
        "RETAILCRM_MG_BOT_TOKEN": result.token,
    }
    if config.mg_api_base:
        updates["RETAILCRM_MG_API_BASE"] = config.mg_api_base
    path = update_env_file(config.env_file, updates)
    print(f"{OK} настройки записаны в {path} (chmod 600)")

    if not config.mg_api_base:
        # Токен уже сохранён — терять его нельзя, иначе понадобится перевыпуск.
        print(
            f"{WARN} адрес MessageGateway неизвестен, проверить подключение нечем.\n"
            f"    Токен сохранён. Допишите в {path} строку\n"
            "    RETAILCRM_MG_API_BASE=https://mg.<домен>/api/bot/v1\n"
            "    и выполните `retailcrm-mg doctor`. Адрес есть в настройках чатов RetailCRM."
        )
        return 1

    mg = MgClient(config.mg_api_base, result.token, http=HttpClient(timeout=config.timeout))
    try:
        channels = take(mg.channels(), 100)
        print(f"{OK} MG отвечает: доступно каналов — {len(channels)}")
    except ConnectorError as exc:
        print(f"{WARN} токен сохранён, но MG не ответил: {exc}")
        return 1
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Проверяет всю цепочку: конфиг → RetailCRM → MessageGateway."""
    config = _config(args)
    report: list[tuple[str, str, str]] = []
    exit_code = 0

    report.append(("Конфиг", OK, str(config.env_file)))

    if not config.base_url:
        report.append(("RetailCRM API", WARN, "адрес не задан (нужен только для bootstrap)"))
    elif config.api_key:
        try:
            _crm(config, config.api_key).ping()
            report.append(("RetailCRM API", OK, f"{config.base_url} · ключ {mask(config.api_key)}"))
        except ConnectorError as exc:
            report.append(("RetailCRM API", FAIL, str(exc)))
            exit_code = 1
    else:
        report.append(("RetailCRM API", WARN, "ключ не задан (нужен только для bootstrap)"))

    if not config.mg_api_base:
        report.append(
            ("MessageGateway", FAIL, "адрес не задан — укажите RETAILCRM_MG_API_BASE")
        )
        exit_code = 1
    elif config.mg_bot_token:
        try:
            mg = _mg(config)
            channels = take(mg.channels(), 100)
            active = [c for c in channels if c.get("activated_at") or c.get("active")]
            report.append(
                (
                    "MessageGateway",
                    OK,
                    f"{config.mg_api_base} · каналов {len(channels)} (активных {len(active)})",
                )
            )
        except ConnectorError as exc:
            report.append(("MessageGateway", FAIL, str(exc)))
            exit_code = 1
    else:
        report.append(("MessageGateway", FAIL, "нет токена — выполните `retailcrm-mg bootstrap`"))
        exit_code = 1

    width = max(len(name) for name, _, _ in report)
    for name, status, detail in report:
        print(f"{status} {name.ljust(width)}  {detail}")
    return exit_code


def cmd_config(args: argparse.Namespace) -> int:
    """Показывает эффективную конфигурацию (секреты замаскированы)."""
    _dump(_config(args).summary())
    return 0


def cmd_modules(args: argparse.Namespace) -> int:
    """Перечисляет integration modules аккаунта — чтобы не затереть чужой."""
    config = _config(args)
    api_key = _resolve_api_key(config, args)
    modules = list(_crm(config, api_key).list_modules())
    if args.json:
        _dump(modules)
        return 0
    _rows(
        modules,
        [("CODE", "code"), ("NAME", "name"), ("ACTIVE", "active"), ("CLIENT ID", "clientId")],
    )
    return 0


def cmd_channels(args: argparse.Namespace) -> int:
    config = _config(args)
    items = take(_mg(config).channels(), args.limit)
    if args.json:
        _dump(items)
        return 0
    _rows(items, [("ID", "id"), ("TYPE", "type"), ("NAME", "name"), ("ACTIVE", "activated_at")])
    return 0


def cmd_chats(args: argparse.Namespace) -> int:
    config = _config(args)
    filters: dict[str, Any] = {}
    if args.channel_id:
        filters["channel_id"] = args.channel_id
    items = take(_mg(config).chats(**filters), args.limit)
    if args.json:
        _dump(items)
        return 0
    _rows(
        items,
        [
            ("ID", "id"),
            ("КЛИЕНТ", "customer.name"),
            ("КАНАЛ", "channel.type"),
            ("АКТИВНОСТЬ", "last_activity"),
        ],
    )
    return 0


def cmd_dialogs(args: argparse.Namespace) -> int:
    config = _config(args)
    filters: dict[str, Any] = {}
    if args.chat_id:
        filters["chat_id"] = args.chat_id
    items = take(_mg(config).dialogs(**filters), args.limit)
    if args.json:
        _dump(items)
        return 0
    _rows(
        items,
        [
            ("ID", "id"),
            ("ЧАТ", "chat_id"),
            ("ОТВЕТСТВЕННЫЙ", "responsible.id"),
            ("ЗАКРЫТ", "closed_at"),
        ],
    )
    return 0


def cmd_messages(args: argparse.Namespace) -> int:
    config = _config(args)
    filters: dict[str, Any] = {}
    if args.chat_id:
        filters["chat_id"] = args.chat_id
    if args.dialog_id:
        filters["dialog_id"] = args.dialog_id
    if args.channel_id:
        filters["channel_id"] = args.channel_id
    items = take(_mg(config).messages(**filters), args.limit)
    if args.json:
        _dump(items)
        return 0
    _rows(
        items,
        [
            ("ID", "id"),
            ("ВРЕМЯ", "time"),
            ("ОТ", "from.name"),
            ("ТИП", "type"),
            ("ТЕКСТ", "content"),
        ],
    )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Выгружает переписки в файлы."""
    config = _config(args)
    transcripts = fetch_transcripts(
        _mg(config),
        limit=args.limit,
        messages_per_chat=args.messages,
        channel_id=args.channel_id,
    )
    written = write_export(transcripts, Path(args.out), fmt=args.format)
    print(f"{OK} записано файлов: {len(written)} → {Path(args.out).expanduser()}")
    return 0


# --------------------------------------------------------------------------
# парсер
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retailcrm-mg",
        description="Коннектор RetailCRM MessageGateway: выпуск токена и выгрузка переписок.",
    )
    parser.add_argument("--version", action="version", version=f"retailcrm-mg {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    parser.add_argument("--env-file", help="путь к .env (по умолчанию ~/.retailcrm-mg/.env)")
    parser.add_argument("--base-url", help="адрес RetailCRM, напр. https://crm.example.com")
    parser.add_argument("--mg-api-base", help="база MG Bot API, напр. https://mg.example.com")

    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser("bootstrap", help="зарегистрировать модуль и выпустить mgBot-токен")
    boot.add_argument("--api-key", help="API-ключ RetailCRM (иначе спросим без эха)")
    boot.add_argument("--ask-key", action="store_true", help="всегда спрашивать ключ интерактивно")
    boot.add_argument("--module-code", help="integrationModule.code")
    boot.add_argument("--module-name", help="человекочитаемое имя модуля")
    boot.add_argument("--client-id", help="integrationModule.clientId")
    boot.add_argument(
        "--refresh", action="store_true", help="перевыпустить токен существующего модуля"
    )
    boot.add_argument("--force", action="store_true", help="не проверять существующий модуль")
    boot.add_argument("--no-write", action="store_true", help="не писать .env")
    boot.add_argument(
        "--dump-response", action="store_true", help="показать разбор ответа RetailCRM"
    )
    boot.set_defaults(func=cmd_bootstrap)

    doctor = sub.add_parser("doctor", help="проверить конфиг, RetailCRM и MG")
    doctor.add_argument("--api-key", help="API-ключ RetailCRM")
    doctor.set_defaults(func=cmd_doctor)

    conf = sub.add_parser("config", help="показать эффективную конфигурацию")
    conf.set_defaults(func=cmd_config)

    modules = sub.add_parser("modules", help="список integration modules аккаунта")
    modules.add_argument("--api-key", help="API-ключ RetailCRM")
    modules.add_argument("--json", action="store_true")
    modules.set_defaults(func=cmd_modules)

    channels = sub.add_parser("channels", help="подключённые каналы MG")
    channels.add_argument("--limit", type=int, default=100)
    channels.add_argument("--json", action="store_true")
    channels.set_defaults(func=cmd_channels)

    chats = sub.add_parser("chats", help="список чатов")
    chats.add_argument("--channel-id", type=int)
    chats.add_argument("--limit", type=int, default=50)
    chats.add_argument("--json", action="store_true")
    chats.set_defaults(func=cmd_chats)

    dialogs = sub.add_parser("dialogs", help="список диалогов")
    dialogs.add_argument("--chat-id", type=int)
    dialogs.add_argument("--limit", type=int, default=50)
    dialogs.add_argument("--json", action="store_true")
    dialogs.set_defaults(func=cmd_dialogs)

    messages = sub.add_parser("messages", help="сообщения чата/диалога")
    messages.add_argument("--chat-id", type=int)
    messages.add_argument("--dialog-id", type=int)
    messages.add_argument("--channel-id", type=int)
    messages.add_argument("--limit", type=int, default=50)
    messages.add_argument("--json", action="store_true")
    messages.set_defaults(func=cmd_messages)

    export = sub.add_parser("export", help="выгрузить переписки в файлы")
    export.add_argument("--out", default="./export", help="каталог назначения")
    export.add_argument("--format", choices=("json", "jsonl", "md"), default="json")
    export.add_argument("--channel-id", type=int)
    export.add_argument("--limit", type=int, default=20, help="сколько чатов выгрузить")
    export.add_argument("--messages", type=int, default=None, help="максимум сообщений на чат")
    export.set_defaults(func=cmd_export)

    # Общие флаги дублируются в подкомандах: и `retailcrm-mg --base-url … bootstrap`,
    # и `retailcrm-mg bootstrap --base-url …` должны работать. default=SUPPRESS
    # обязателен — иначе подкоманда затрёт значение, заданное до неё.
    for parser_obj in sub.choices.values():
        _add_shared_flags(parser_obj)

    return parser


def _add_shared_flags(parser: argparse.ArgumentParser) -> None:
    """Добавляет глобальные флаги в подкоманду, не затирая значения из общей части."""
    for flag, help_text in (
        ("--env-file", "путь к .env"),
        ("--base-url", "адрес RetailCRM, напр. https://crm.example.com"),
        ("--mg-api-base", "база MG Bot API, напр. https://mg.example.com/api/bot/v1"),
    ):
        parser.add_argument(flag, help=help_text, default=argparse.SUPPRESS)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        return int(args.func(args) or 0)
    except ConfigError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    except ConnectorError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\nпрервано", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
