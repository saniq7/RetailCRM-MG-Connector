"""Минимальный HTTP-клиент поверх стандартной библиотеки.

Никаких внешних зависимостей: коннектор должен разворачиваться на голом
сервере, где есть только Python 3.9+.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from .errors import ApiError, AuthError, NotFoundError, RateLimitError

logger = logging.getLogger(__name__)

USER_AGENT = "retailcrm-mg-connector/1.0 (+https://github.com/saniq7/RetailCRM-MG-Connector)"

#: Коды, которые имеет смысл повторить.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def build_url(base: str, path: str, params: Mapping[str, Any] | None = None) -> str:
    """Склеивает базовый URL, путь и query-параметры.

    ``None``-значения в ``params`` отбрасываются, булевы приводятся к
    ``true``/``false`` — так их ждут обе стороны интеграции.
    """
    url = base.rstrip("/") + "/" + path.lstrip("/")
    if not params:
        return url
    clean: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean[key] = "true" if value else "false"
        else:
            clean[key] = str(value)
    if not clean:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urllib.parse.urlencode(clean)}"


class HttpClient:
    """Тонкая обёртка над ``urllib`` с ретраями и разбором JSON."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        backoff: float = 1.0,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff = backoff
        self.user_agent = user_agent

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        """Выполняет запрос и возвращает разобранный JSON.

        Тело ответа, которое не парсится как JSON, возвращается в виде
        ``{"raw": "..."}`` — так вызывающий код всегда работает со словарём.
        """
        data: bytes | None = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if form is not None:
            data = urllib.parse.urlencode(_flatten_form(form)).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode()
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)

        last_error: ApiError | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._once(method, url, data, request_headers)
            except (RateLimitError, ApiError) as exc:
                retriable = isinstance(exc, RateLimitError) or (
                    exc.status in RETRY_STATUSES or exc.status is None
                )
                if not retriable or attempt == self.retries:
                    raise
                last_error = exc
                delay = self.backoff * (2**attempt)
                logger.warning(
                    "%s %s -> %s, повтор через %.1f с (попытка %d/%d)",
                    method,
                    _redact(url),
                    exc.status,
                    delay,
                    attempt + 1,
                    self.retries,
                )
                time.sleep(delay)
        raise last_error or ApiError("запрос не выполнен", url=_redact(url))

    def _once(
        self,
        method: str,
        url: str,
        data: bytes | None,
        headers: Mapping[str, str],
    ) -> Any:
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return _parse(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            body = _parse(raw)
            raise _classify(exc.code, url, body) from None
        except urllib.error.URLError as exc:
            raise ApiError(f"сеть недоступна: {exc.reason}", url=_redact(url)) from None

    # -- сахар ------------------------------------------------------------

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> Any:
        return self.request("GET", url, headers=headers)

    def post_form(
        self,
        url: str,
        form: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return self.request("POST", url, headers=headers, form=form)


def _parse(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return {"raw": raw}


def _classify(status: int, url: str, body: Any) -> ApiError:
    message = _message(body) or f"запрос отклонён ({status})"
    safe_url = _redact(url)
    if status in (401, 403):
        return AuthError(message, status=status, url=safe_url, body=body)
    if status == 404:
        return NotFoundError(message, status=status, url=safe_url, body=body)
    if status == 429:
        return RateLimitError(message, status=status, url=safe_url, body=body)
    return ApiError(message, status=status, url=safe_url, body=body)


def _message(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("errorMsg", "error_msg", "message", "error"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    errors = body.get("errors")
    if isinstance(errors, dict) and errors:
        return "; ".join(f"{k}: {v}" for k, v in errors.items())
    if isinstance(errors, list) and errors:
        return "; ".join(str(item) for item in errors)
    return None


def _flatten_form(form: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in form.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def _redact(url: str) -> str:
    """Прячет ``apiKey`` в URL, чтобы он не утёк в логи и трейсбеки."""
    split = urllib.parse.urlsplit(url)
    if not split.query:
        return url
    pairs = urllib.parse.parse_qsl(split.query, keep_blank_values=True)
    masked = [(k, "***" if k.lower() in {"apikey", "token"} else v) for k, v in pairs]
    return urllib.parse.urlunsplit(split._replace(query=urllib.parse.urlencode(masked)))
