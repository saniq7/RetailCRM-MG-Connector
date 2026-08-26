"""Конфигурация коннектора: чтение ``.env``, нормализация адресов, маскирование.

Адреса RetailCRM и MessageGateway у каждого аккаунта свои, поэтому у коннектора
нет «значений по умолчанию» для них: их задаёт пользователь.
"""

from __future__ import annotations

import os
import re
import socket
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

#: Стандартный путь Bot API внутри MessageGateway.
MG_API_PATH = "/api/bot/v1"

#: Куда коннектор пишет и откуда читает настройки по умолчанию.
DEFAULT_HOME = Path(os.environ.get("RETAILCRM_MG_HOME", Path.home() / ".retailcrm-mg"))
DEFAULT_ENV_FILE = DEFAULT_HOME / ".env"

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_CODE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def slug_hostname(raw: str | None = None) -> str:
    """Нормализует hostname до ``[a-z0-9_-]`` — RetailCRM не примет иное."""
    host = (raw or socket.gethostname() or "").lower()
    host = _SLUG_RE.sub("-", host).strip("-")
    return host or "server"


def normalize_code(code: str) -> str:
    """Приводит ``integrationModule.code`` к допустимому виду."""
    cleaned = _CODE_RE.sub("_", code).strip("_")
    if not cleaned:
        raise ConfigError("код модуля пуст после нормализации")
    return cleaned


def _with_scheme(value: str | None) -> str:
    """Добавляет ``https://``, если пользователь указал только хост."""
    raw = (value or "").strip()
    if not raw:
        return ""
    return raw if "://" in raw else f"https://{raw}"


def _is_valid(split: urllib.parse.SplitResult) -> bool:
    """Адрес пригоден, если это http(s) и в хосте есть что-то осмысленное."""
    if split.scheme not in ("http", "https"):
        return False
    host = split.netloc.split("@")[-1].split(":")[0]
    return bool(host) and any(ch.isalnum() for ch in host)


def normalize_base_url(value: str) -> str:
    """Приводит адрес RetailCRM к каноничному виду.

    Принимает и ``crm.example.com``, и ``https://crm.example.com/api/v5/``,
    возвращает ``https://crm.example.com``. Адрес аккаунта у каждого свой —
    значения по умолчанию у коннектора нет.
    """
    raw = _with_scheme(value)
    if not raw:
        raise ConfigError("адрес RetailCRM пуст")
    split = urllib.parse.urlsplit(raw)
    if not _is_valid(split):
        raise ConfigError(f"некорректный адрес RetailCRM: {value!r}")
    path = split.path.rstrip("/")
    # Пользователи часто копируют адрес вместе с путём API — отрезаем его.
    if path.endswith("/api/v5"):
        path = path[: -len("/api/v5")]
    return urllib.parse.urlunsplit((split.scheme, split.netloc, path, "", ""))


def normalize_mg_api_base(value: str) -> str:
    """Приводит адрес MessageGateway к базе Bot API.

    ``mg.example.com`` → ``https://mg.example.com/api/bot/v1``;
    уже указанный путь сохраняется как есть.
    """
    raw = _with_scheme(value)
    if not raw:
        raise ConfigError("адрес MessageGateway пуст")
    split = urllib.parse.urlsplit(raw)
    if not _is_valid(split):
        raise ConfigError(f"некорректный адрес MessageGateway: {value!r}")
    path = split.path.rstrip("/") or MG_API_PATH
    return urllib.parse.urlunsplit((split.scheme, split.netloc, path, "", ""))


def mask(secret: str | None, *, head: int = 6, tail: int = 4) -> str:
    """Маскирует секрет для логов и отчётов: ``abc123...wxyz``."""
    if not secret:
        return "<не задан>"
    if len(secret) <= head + tail:
        return "*" * len(secret)
    return f"{secret[:head]}...{secret[-tail:]}"


def parse_env_text(text: str) -> dict[str, str]:
    """Разбирает содержимое ``.env``: ``KEY=VALUE``, ``#`` — комментарий."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(path: Path) -> dict[str, str]:
    """Читает ``.env``; отсутствующий файл — не ошибка."""
    if not path.exists():
        return {}
    return parse_env_text(path.read_text(encoding="utf-8"))


@dataclass
class Config:
    """Все настройки коннектора в одном месте."""

    base_url: str = ""
    api_key: str | None = None
    mg_api_base: str = ""
    mg_bot_token: str | None = None
    module_code: str = ""
    module_name: str = ""
    client_id: str = ""
    env_file: Path = field(default=DEFAULT_ENV_FILE)
    timeout: float = 30.0

    @classmethod
    def load(
        cls,
        *,
        env_file: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> Config:
        """Собирает конфиг: ``.env`` < переменные окружения.

        Адреса не подставляются: пустое значение так и остаётся пустым,
        а команда, которой адрес нужен, скажет об этом явно.
        """
        environ = os.environ if environ is None else environ
        raw_path = env_file or environ.get("RETAILCRM_MG_ENV_FILE") or DEFAULT_ENV_FILE
        path = Path(raw_path).expanduser()
        merged: dict[str, str] = {}
        merged.update(load_env_file(path))
        merged.update({k: v for k, v in environ.items() if k.startswith("RETAILCRM_")})

        host = slug_hostname()
        code = normalize_code(merged.get("RETAILCRM_MG_MODULE_CODE") or f"mg_connector_{host}")
        return cls(
            base_url=_maybe(normalize_base_url, merged.get("RETAILCRM_BASE_URL")),
            api_key=merged.get("RETAILCRM_API_KEY") or None,
            mg_api_base=_maybe(normalize_mg_api_base, merged.get("RETAILCRM_MG_API_BASE")),
            mg_bot_token=merged.get("RETAILCRM_MG_BOT_TOKEN") or None,
            module_code=code,
            module_name=merged.get("RETAILCRM_MG_MODULE_NAME") or f"MG connector {host}",
            client_id=merged.get("RETAILCRM_MG_CLIENT_ID") or f"mg-connector-{host}",
            env_file=path,
            timeout=float(merged.get("RETAILCRM_MG_TIMEOUT") or 30.0),
        )

    def require_base_url(self) -> str:
        if not self.base_url:
            raise ConfigError(
                "не задан адрес RetailCRM. Укажите --base-url https://<ваш-аккаунт> "
                "или переменную RETAILCRM_BASE_URL"
            )
        return self.base_url

    def require_api_key(self) -> str:
        if not self.api_key:
            raise ConfigError(
                "не задан RETAILCRM_API_KEY. Передайте --api-key, переменную окружения "
                "или сохраните ключ в .env"
            )
        return self.api_key

    def require_mg_api_base(self) -> str:
        if not self.mg_api_base:
            raise ConfigError(
                "не задан адрес MessageGateway. Укажите --mg-api-base https://mg.<домен> "
                "или переменную RETAILCRM_MG_API_BASE"
            )
        return self.mg_api_base

    def require_bot_token(self) -> str:
        if not self.mg_bot_token:
            raise ConfigError(
                "не задан RETAILCRM_MG_BOT_TOKEN. Сначала выполните `retailcrm-mg bootstrap`"
            )
        return self.mg_bot_token

    def summary(self) -> dict[str, str]:
        """Безопасное для вывода описание конфигурации."""
        return {
            "base_url": self.base_url or "<не задан>",
            "api_key": mask(self.api_key),
            "mg_api_base": self.mg_api_base or "<не задан>",
            "mg_bot_token": mask(self.mg_bot_token),
            "module_code": self.module_code,
            "module_name": self.module_name,
            "client_id": self.client_id,
            "env_file": str(self.env_file),
        }


def _maybe(normalizer, value: str | None) -> str:
    """Нормализует значение, если оно задано; пустое остаётся пустым."""
    return normalizer(value) if value else ""
