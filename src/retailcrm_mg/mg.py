"""Клиент MessageGateway Bot API (``X-Bot-Token``).

Через него коннектор и «тянет переписки»: каналы → чаты → диалоги → сообщения.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import Any

from .errors import ApiError
from .http import HttpClient, build_url

logger = logging.getLogger(__name__)

#: Максимум, который MG отдаёт за один запрос.
MAX_LIMIT = 100


class MgClient:
    """Клиент Bot API MessageGateway.

    Все листинги идут через курсорную пагинацию ``since_id``: MG возвращает
    страницу, отсортированную по ``id``, следующий запрос стартует с последнего
    полученного идентификатора.
    """

    def __init__(
        self,
        api_base: str,
        bot_token: str,
        *,
        http: HttpClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.bot_token = bot_token
        self.http = http or HttpClient(timeout=timeout)

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Bot-Token": self.bot_token}

    # -- низкий уровень ---------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = build_url(self.api_base, path, params)
        return self.http.get(url, headers=self.headers)

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int = MAX_LIMIT,
        max_items: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Перебирает все элементы листинга, страница за страницей."""
        page_size = max(1, min(limit, MAX_LIMIT))
        since_id: int | None = None
        yielded = 0
        while True:
            query = dict(params or {})
            query["limit"] = page_size
            if since_id is not None:
                query["since_id"] = since_id
            batch = self.get(path, query)
            if not isinstance(batch, list):
                raise ApiError(
                    f"MG вернул неожиданный ответ для {path}",
                    url=build_url(self.api_base, path),
                    body=batch,
                )
            if not batch:
                return
            for item in batch:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            last_id = batch[-1].get("id")
            if last_id is None or last_id == since_id:
                return
            since_id = last_id
            if len(batch) < page_size:
                return

    # -- ресурсы ----------------------------------------------------------

    def ping(self) -> list[dict[str, Any]]:
        """Дешёвая проверка токена."""
        result = self.get("/channels", {"limit": 1})
        if not isinstance(result, list):
            raise ApiError("MG не подтвердил токен", url=f"{self.api_base}/channels", body=result)
        return result

    def channels(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """Подключённые каналы: WhatsApp, Telegram, VK, e-mail и т.д."""
        return self.paginate("/channels", params=filters)

    def chats(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """Чаты — верхнеуровневые переписки с клиентами."""
        return self.paginate("/chats", params=filters)

    def dialogs(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """Диалоги — отрезки чата, назначенные на оператора или бота."""
        return self.paginate("/dialogs", params=filters)

    def members(self, **filters: Any) -> Iterator[dict[str, Any]]:
        return self.paginate("/members", params=filters)

    def messages(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """Сообщения. Фильтруются по ``chat_id``, ``dialog_id``, ``channel_id``."""
        return self.paginate("/messages", params=filters)

    def customers(self, **filters: Any) -> Iterator[dict[str, Any]]:
        return self.paginate("/customers", params=filters)

    def users(self, **filters: Any) -> Iterator[dict[str, Any]]:
        return self.paginate("/users", params=filters)

    def chat_messages(
        self, chat_id: int, *, max_items: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Все сообщения одного чата в хронологическом порядке."""
        return self.paginate("/messages", params={"chat_id": chat_id}, max_items=max_items)


def take(iterable: Iterable[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    """Материализует итератор, не читая лишнего."""
    if limit is None:
        return list(iterable)
    out: list[dict[str, Any]] = []
    for item in iterable:
        out.append(item)
        if len(out) >= limit:
            break
    return out
