"""Клиент RetailCRM API v5 — ровно та часть, что нужна для выпуска mgBot-токена."""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .config import normalize_code
from .errors import ApiError, AuthError, TokenNotIssuedError
from .http import HttpClient, build_url

logger = logging.getLogger(__name__)

#: Права, без которых не выпустить токен.
REQUIRED_CREDENTIALS = ("/api/integration-modules/{code}/edit",)

#: Наиболее вероятные места, где RetailCRM возвращает свежий mgBot-токен.
TOKEN_PATHS = (
    ("info", "mgBot", "token"),
    ("integrationModule", "integrations", "mgBot", "token"),
    ("integrations", "mgBot", "token"),
    ("mgBot", "token"),
)

#: Где в ответе может лежать адрес MessageGateway этого аккаунта.
ENDPOINT_PATHS = (
    ("info", "mgBot", "endpointUrl"),
    ("info", "mgBot", "url"),
    ("integrationModule", "integrations", "mgBot", "endpointUrl"),
    ("integrations", "mgBot", "endpointUrl"),
)


@dataclass
class BootstrapResult:
    """Итог регистрации/обновления integration module."""

    module_code: str
    module_name: str
    client_id: str
    token: str
    created: bool
    raw: dict[str, Any]
    #: Адрес MG, если RetailCRM вернул его в ответе. Иначе задаётся пользователем.
    mg_api_base: str | None = None


class RetailCrmClient:
    """Обёртка над ``/api/v5`` конкретного аккаунта RetailCRM."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        http: HttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.http = http or HttpClient(timeout=timeout)

    # -- низкий уровень ---------------------------------------------------

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        query = dict(params or {})
        query["apiKey"] = self.api_key
        return build_url(self.base_url, f"/api/v5{path}", query)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.http.get(self._url(path, params))

    # -- публичные методы -------------------------------------------------

    def ping(self) -> dict[str, Any]:
        """Проверяет, что ключ жив: ``GET /reference/sites``."""
        body = self._get("/reference/sites")
        if not body.get("success"):
            raise ApiError(
                "RetailCRM не подтвердил ключ",
                url=f"{self.base_url}/api/v5/reference/sites",
                body=body,
            )
        return body

    def credentials(self) -> dict[str, Any]:
        """Возвращает список прав ключа: ``GET /credentials``."""
        return self._get("/credentials")

    def missing_credentials(self, code: str) -> list[str]:
        """Проверяет, хватает ли ключу прав на работу с integration modules."""
        try:
            body = self.credentials()
        except ApiError:
            # /credentials доступен не во всех редакциях — не блокируем работу.
            return []
        granted = set(body.get("credentials") or [])
        if not granted:
            return []
        missing = []
        for template in REQUIRED_CREDENTIALS:
            needed = template.format(code=code)
            if needed not in granted:
                missing.append(needed)
        return missing

    def get_module(self, code: str) -> dict[str, Any] | None:
        """Читает integration module или возвращает ``None``, если его нет."""
        code = normalize_code(code)
        quoted = urllib.parse.quote(code, safe="")
        try:
            body = self._get(f"/integration-modules/{quoted}")
        except AuthError:
            raise
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise
        if not body.get("success"):
            return None
        return body.get("integrationModule")

    def list_modules(self) -> Iterator[dict[str, Any]]:
        """Перебирает все integration modules аккаунта (постранично)."""
        page = 1
        while True:
            body = self._get("/integration-modules", {"page": page, "limit": 100})
            modules = body.get("integrationModules") or []
            yield from modules
            pagination = body.get("pagination") or {}
            if page >= int(pagination.get("totalPageCount") or page):
                return
            page += 1

    def bootstrap_mg_bot(
        self,
        *,
        code: str,
        name: str,
        client_id: str,
        active: bool = True,
        refresh_token: bool = True,
    ) -> BootstrapResult:
        """Создаёт/обновляет модуль и просит RetailCRM выпустить mgBot-токен.

        Ключевой параметр — ``integrationModule[integrations][mgBot][refreshToken]``:
        именно он заставляет MessageGateway выдать новый токен, вместо того чтобы
        переносить старый с другого сервера.
        """
        code = normalize_code(code)
        existing = self.get_module(code)
        quoted = urllib.parse.quote(code, safe="")
        form = {
            "integrationModule[code]": code,
            "integrationModule[integrationCode]": code,
            "integrationModule[clientId]": client_id,
            "integrationModule[name]": name,
            "integrationModule[active]": active,
            "integrationModule[integrations][mgBot][refreshToken]": refresh_token,
        }
        body = self.http.post_form(self._url(f"/integration-modules/{quoted}/edit"), form)
        if not body.get("success"):
            raise ApiError(
                "RetailCRM отклонил регистрацию модуля",
                url=f"{self.base_url}/api/v5/integration-modules/{quoted}/edit",
                body=body,
            )
        token = extract_token(body)
        if not token:
            raise TokenNotIssuedError(
                "RetailCRM принял модуль, но не вернул mgBot-токен. "
                "Проверьте, что у аккаунта подключён MessageGateway, "
                "и посмотрите полный ответ: retailcrm-mg bootstrap --dump-response"
            )
        return BootstrapResult(
            module_code=code,
            module_name=name,
            client_id=client_id,
            token=token,
            created=existing is None,
            raw=body,
            mg_api_base=extract_mg_endpoint(body),
        )


def extract_token(body: Any) -> str | None:
    """Достаёт mgBot-токен из ответа RetailCRM.

    Сначала пробуем известные пути, потом — обход дерева: формат ответа
    отличается между версиями RetailCRM.
    """
    for path in TOKEN_PATHS:
        value = _dig(body, path)
        if isinstance(value, str) and len(value) >= 12:
            return value
    candidates = sorted(find_token_candidates(body), key=lambda item: (len(item[0]), item[0]))
    return candidates[0][1] if candidates else None


def extract_mg_endpoint(body: Any) -> str | None:
    """Пытается вытащить адрес MessageGateway из ответа RetailCRM.

    RetailCRM отдаёт его не всегда и не во всех версиях, поэтому это лишь
    удобство: если адрес не нашёлся, пользователь указывает его сам.
    """
    for path in ENDPOINT_PATHS:
        value = _dig(body, path)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    for path, value in _find_url_candidates(body):
        if "mg" in path.lower():
            return value
    return None


def _find_url_candidates(node: Any, path: str = "") -> list[tuple[str, str]]:
    """Ищет строковые поля, похожие на URL, вместе с их путями в ответе."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            if (
                isinstance(value, str)
                and value.startswith(("http://", "https://"))
                and ("url" in lowered or "endpoint" in lowered or "host" in lowered)
            ):
                found.append((child, value))
            found.extend(_find_url_candidates(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_find_url_candidates(value, f"{path}[{index}]"))
    return found


def find_token_candidates(node: Any, path: str = "") -> list[tuple[str, str]]:
    """Ищет все строковые поля, похожие на токен, вместе с их путями."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, str) and "token" in str(key).lower() and len(value) >= 12:
                found.append((child, value))
            found.extend(find_token_candidates(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(find_token_candidates(value, f"{path}[{index}]"))
    return found


def _dig(node: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node
