import stat
from pathlib import Path

from retailcrm_mg.envfile import read_env_file, render_env, update_env_file


def test_render_env_updates_in_place_and_keeps_comments():
    existing = "# заголовок\nRETAILCRM_BASE_URL=https://old\nOTHER=1\n"
    result = render_env(existing, {"RETAILCRM_BASE_URL": "https://new", "NEW_KEY": "2"})
    assert result.splitlines() == [
        "# заголовок",
        "RETAILCRM_BASE_URL=https://new",
        "OTHER=1",
        "NEW_KEY=2",
    ]


def test_render_env_collapses_duplicate_keys():
    existing = "TOKEN=a\nTOKEN=b\n"
    assert render_env(existing, {"TOKEN": "c"}) == "TOKEN=c\n"


def test_update_env_file_is_idempotent_and_private(tmp_path: Path):
    path = tmp_path / "nested" / ".env"
    updates = {"RETAILCRM_MG_BOT_TOKEN": "t0ken-value-123"}
    update_env_file(path, updates)
    update_env_file(path, updates)

    assert path.read_text(encoding="utf-8").count("RETAILCRM_MG_BOT_TOKEN") == 1
    assert read_env_file(path)["RETAILCRM_MG_BOT_TOKEN"] == "t0ken-value-123"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
