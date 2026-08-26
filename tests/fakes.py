"""Подменный HTTP-клиент: тесты не ходят в сеть."""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from retailcrm_mg.errors import ApiError


class FakeHttp:
    """Реализует интерфейс ``HttpClient`` поверх словаря маршрутов."""

    def __init__(self, routes: dict[str, Any] | None = None) -> None:
        self.routes: dict[str, Any] = routes or {}
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def route(self, path: str, response: Any) -> FakeHttp:
        self.routes[path] = response
        return self

    def request(self, method, url, *, headers=None, form=None, json_body=None):
        split = urlsplit(url)
        query = {k: v[0] for k, v in parse_qs(split.query).items()}
        self.calls.append((method.upper(), split.path, form or query))
        handler = self.routes.get(split.path)
        if handler is None:
            raise ApiError("нет маршрута в фейке", status=404, url=split.path)
        if isinstance(handler, Callable):  # type: ignore[arg-type]
            return handler(query, form)
        return handler

    def get(self, url, *, headers=None):
        return self.request("GET", url, headers=headers)

    def post_form(self, url, form, *, headers=None):
        return self.request("POST", url, headers=headers, form=form)
