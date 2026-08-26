from pathlib import Path

from fakes import FakeHttp
from retailcrm_mg.export import (
    Transcript,
    fetch_transcripts,
    normalize_message,
    to_markdown,
    write_export,
)
from retailcrm_mg.mg import MgClient

CHAT = {
    "id": 7,
    "channel": {"type": "telegram"},
    "customer": {"name": "Иван"},
    "created_at": "2026-08-20T10:00:00Z",
}
MESSAGES = [
    {"id": 1, "time": "2026-08-20T10:01:00Z", "type": "text", "content": "Здравствуйте",
     "from": {"type": "customer", "name": "Иван"}},
    {"id": 2, "time": "2026-08-20T10:02:00Z", "type": "text", "content": "Добрый день!",
     "from": {"type": "user", "name": "Оператор"}},
]


def build_client() -> MgClient:
    http = FakeHttp(
        {
            "/api/bot/v1/chats": lambda q, f: [] if q.get("since_id") else [CHAT],
            "/api/bot/v1/messages": lambda q, f: [] if q.get("since_id") else MESSAGES,
        }
    )
    return MgClient("https://mg.example.ru/api/bot/v1", "token", http=http)


def test_normalize_message_detects_direction_and_author():
    incoming = normalize_message(MESSAGES[0])
    outgoing = normalize_message(MESSAGES[1])
    assert incoming["direction"] == "in"
    assert incoming["author"] == "Иван"
    assert outgoing["direction"] == "out"


def test_transcript_title_falls_back_to_customer_name():
    assert Transcript(chat=CHAT).title == "Иван"
    assert Transcript(chat={"id": 3}).title == "chat-3"
    assert Transcript(chat={"id": 3}).channel == "unknown"


def test_fetch_transcripts_pulls_chat_with_messages():
    transcripts = list(fetch_transcripts(build_client(), limit=1))
    assert len(transcripts) == 1
    assert [m["id"] for m in transcripts[0].messages] == [1, 2]
    assert transcripts[0].to_dict()["messages"][0]["text"] == "Здравствуйте"


def test_to_markdown_renders_both_sides():
    transcript = list(fetch_transcripts(build_client(), limit=1))[0]
    rendered = to_markdown(transcript)
    assert "# Иван" in rendered
    assert "> Здравствуйте" in rendered
    assert "Оператор" in rendered


def test_write_export_json_and_markdown(tmp_path: Path):
    transcripts = list(fetch_transcripts(build_client(), limit=1))
    json_files = write_export(transcripts, tmp_path / "json", fmt="json")
    md_files = write_export(transcripts, tmp_path / "md", fmt="md")
    jsonl_files = write_export(transcripts, tmp_path / "jsonl", fmt="jsonl")

    assert json_files[0].name == "chat-7.json"
    assert md_files[0].name == "chat-7.md"
    assert jsonl_files[0].name == "transcripts.jsonl"
    assert jsonl_files[0].read_text(encoding="utf-8").strip().count("\n") == 0
