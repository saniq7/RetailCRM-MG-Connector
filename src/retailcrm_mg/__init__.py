"""RetailCRM MG Connector — доступ к чатам RetailCRM через MessageGateway Bot API."""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = [
    "Config",
    "MgClient",
    "RetailCrmClient",
    "Transcript",
    "__version__",
]


def __getattr__(name: str):  # pragma: no cover - ленивый реэкспорт
    if name == "Config":
        from .config import Config

        return Config
    if name == "MgClient":
        from .mg import MgClient

        return MgClient
    if name == "RetailCrmClient":
        from .retailcrm import RetailCrmClient

        return RetailCrmClient
    if name == "Transcript":
        from .export import Transcript

        return Transcript
    raise AttributeError(name)
