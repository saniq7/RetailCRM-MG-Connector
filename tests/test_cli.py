import json
from pathlib import Path

from retailcrm_mg import cli
from retailcrm_mg.cli import build_parser, main


def test_parser_exposes_all_commands():
    parser = build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None)]
    commands = set(actions[-1].choices)
    expected = {"bootstrap", "doctor", "config", "modules", "channels", "chats", "messages"}
    assert expected <= commands


def test_config_command_masks_secrets(tmp_path: Path, capsys, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("RETAILCRM_API_KEY=super-secret-key-value\n", encoding="utf-8")
    monkeypatch.delenv("RETAILCRM_API_KEY", raising=False)

    assert main(["--env-file", str(env_file), "config"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["api_key"] == "super-...alue"
    assert "super-secret-key-value" not in json.dumps(printed)


def test_doctor_fails_without_token(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("RETAILCRM_MG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RETAILCRM_API_KEY", raising=False)

    assert main(["--env-file", str(tmp_path / "empty.env"), "doctor"]) == 1
    assert "bootstrap" in capsys.readouterr().out


def test_channels_command_prints_table(tmp_path: Path, capsys, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "RETAILCRM_MG_BOT_TOKEN=example-token-value\nRETAILCRM_MG_API_BASE=https://mg.example.com\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("RETAILCRM_MG_BOT_TOKEN", raising=False)

    class StubMg:
        def channels(self):
            return iter([{"id": 1, "type": "telegram", "name": "Основной"}])

    monkeypatch.setattr(cli, "_mg", lambda config: StubMg())
    assert main(["--env-file", str(env_file), "channels"]) == 0
    out = capsys.readouterr().out
    assert "telegram" in out and "Основной" in out


def test_missing_address_returns_exit_code_two(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("RETAILCRM_MG_API_BASE", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["--env-file", str(tmp_path / "none.env"), "chats"]) == 2
    assert "адрес MessageGateway" in capsys.readouterr().err


def test_missing_token_returns_exit_code_two(tmp_path: Path, capsys, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("RETAILCRM_MG_API_BASE=https://mg.example.com\n", encoding="utf-8")
    monkeypatch.delenv("RETAILCRM_MG_BOT_TOKEN", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["--env-file", str(env_file), "chats"]) == 2
    assert "bootstrap" in capsys.readouterr().err
