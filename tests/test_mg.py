import pytest

from fakes import FakeHttp
from retailcrm_mg.errors import ApiError
from retailcrm_mg.mg import MgClient, take


def make_client(http: FakeHttp) -> MgClient:
    return MgClient("https://mg.example.ru/api/bot/v1", "bot-token", http=http)


def test_headers_carry_bot_token():
    assert make_client(FakeHttp()).headers == {"X-Bot-Token": "bot-token"}


def test_paginate_follows_since_id_cursor():
    pages = {
        None: [{"id": n} for n in range(1, 4)],
        "3": [{"id": n} for n in range(4, 6)],
    }

    def handler(query, form):
        return pages.get(query.get("since_id"), [])

    http = FakeHttp({"/api/bot/v1/chats": handler})
    items = list(make_client(http).paginate("/chats", limit=3))

    assert [item["id"] for item in items] == [1, 2, 3, 4, 5]
    # Короткая страница завершает обход без лишнего запроса.
    assert len(http.calls) == 2


def test_paginate_stops_on_max_items():
    http = FakeHttp({"/api/bot/v1/messages": lambda q, f: [{"id": n} for n in range(1, 101)]})
    items = list(make_client(http).paginate("/messages", limit=100, max_items=4))
    assert [item["id"] for item in items] == [1, 2, 3, 4]


def test_paginate_rejects_non_list_payload():
    http = FakeHttp({"/api/bot/v1/chats": {"errors": ["invalid token"]}})
    with pytest.raises(ApiError):
        list(make_client(http).paginate("/chats"))


def test_chat_messages_filters_by_chat_id():
    seen = {}

    def handler(query, form):
        seen.update(query)
        return [{"id": 1, "content": "привет"}]

    http = FakeHttp({"/api/bot/v1/messages": handler})
    messages = list(make_client(http).chat_messages(42))

    assert messages[0]["content"] == "привет"
    assert seen["chat_id"] == "42"


def test_take_reads_only_requested_amount():
    def gen():
        for n in range(1000):
            yield {"id": n}

    assert len(take(gen(), 3)) == 3
    assert len(take([{"id": 1}], None)) == 1
