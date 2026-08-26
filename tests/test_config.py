from pathlib import Path

import pytest

from retailcrm_mg.config import (
    Config,
    mask,
    normalize_base_url,
    normalize_code,
    normalize_mg_api_base,
    parse_env_text,
    slug_hostname,
)
from retailcrm_mg.errors import ConfigError


def test_parse_env_text_handles_comments_quotes_and_export():
    parsed = parse_env_text(
        "\n".join(
            [
                "# комментарий",
                "RETAILCRM_BASE_URL=https://crm.example.com",
                'export RETAILCRM_API_KEY="secret-value"',
                "  ",
                "BROKEN_LINE",
            ]
        )
    )
    assert parsed["RETAILCRM_BASE_URL"] == "https://crm.example.com"
    assert parsed["RETAILCRM_API_KEY"] == "secret-value"
    assert "BROKEN_LINE" not in parsed


def test_slug_hostname_strips_forbidden_characters():
    assert slug_hostname("Server.Example.COM") == "server-example-com"
    assert slug_hostname("!!!") == "server"


def test_normalize_code_rejects_empty():
    assert normalize_code("hermes mg/01") == "hermes_mg_01"
    with pytest.raises(ConfigError):
        normalize_code("///")


def test_mask_never_leaks_full_secret():
    assert mask("abcdef1234567890wxyz") == "abcdef...wxyz"
    assert mask("short") == "*****"
    assert mask(None) == "<не задан>"


def test_env_is_overridden_by_process_environment(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "RETAILCRM_BASE_URL=https://from-file.example.com\nRETAILCRM_MG_MODULE_CODE=from_file\n",
        encoding="utf-8",
    )
    config = Config.load(
        env_file=env_file,
        environ={"RETAILCRM_BASE_URL": "https://from-env.example.com"},
    )
    assert config.base_url == "https://from-env.example.com"
    assert config.module_code == "from_file"
    assert config.summary()["api_key"] == "<не задан>"


def test_require_api_key_raises_with_hint(tmp_path: Path):
    config = Config.load(env_file=tmp_path / "absent.env", environ={})
    with pytest.raises(ConfigError, match="RETAILCRM_API_KEY"):
        config.require_api_key()


def test_addresses_have_no_defaults(tmp_path: Path):
    """Адреса привязаны к конкретному аккаунту — коннектор их не выдумывает."""
    config = Config.load(env_file=tmp_path / "absent.env", environ={})
    assert config.base_url == ""
    assert config.mg_api_base == ""
    assert config.summary()["base_url"] == "<не задан>"
    assert config.summary()["mg_api_base"] == "<не задан>"

    with pytest.raises(ConfigError, match="адрес RetailCRM"):
        config.require_base_url()
    with pytest.raises(ConfigError, match="адрес MessageGateway"):
        config.require_mg_api_base()


def test_normalize_base_url_accepts_common_user_input():
    assert normalize_base_url("crm.example.com") == "https://crm.example.com"
    assert normalize_base_url("https://crm.example.com/") == "https://crm.example.com"
    # Адрес часто копируют вместе с путём API — он должен отрезаться.
    assert normalize_base_url("https://crm.example.com/api/v5") == "https://crm.example.com"
    assert normalize_base_url("http://localhost:8080") == "http://localhost:8080"


def test_normalize_base_url_rejects_garbage():
    for bad in ("", "   ", "ftp://crm.example.com", "https://"):
        with pytest.raises(ConfigError):
            normalize_base_url(bad)


def test_normalize_mg_api_base_appends_bot_api_path():
    assert normalize_mg_api_base("mg.example.com") == "https://mg.example.com/api/bot/v1"
    assert (
        normalize_mg_api_base("https://mg.example.com/api/bot/v1/")
        == "https://mg.example.com/api/bot/v1"
    )
    # Нестандартный путь оставляем как есть.
    assert (
        normalize_mg_api_base("https://mg.example.com/custom/path")
        == "https://mg.example.com/custom/path"
    )
