"""Исключения коннектора."""

from __future__ import annotations


class ConnectorError(Exception):
    """Базовая ошибка коннектора."""


class ConfigError(ConnectorError):
    """Не хватает или некорректна конфигурация."""


class ApiError(ConnectorError):
    """Ошибка HTTP-запроса к RetailCRM или MessageGateway."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        url: str | None = None,
        body: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.url = url
        self.body = body

    def __str__(self) -> str:  # pragma: no cover - тривиальное форматирование
        parts = [super().__str__()]
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.url:
            parts.append(self.url)
        return " | ".join(parts)


class AuthError(ApiError):
    """Ключ/токен отклонён (401/403)."""


class NotFoundError(ApiError):
    """Ресурс не найден (404)."""


class RateLimitError(ApiError):
    """Слишком много запросов (429)."""


class TokenNotIssuedError(ConnectorError):
    """RetailCRM принял запрос, но не вернул mgBot-токен."""
