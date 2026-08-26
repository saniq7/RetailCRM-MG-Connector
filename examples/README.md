# Примеры

| Файл | Что показывает |
|---|---|
| [`export_transcripts.py`](export_transcripts.py) | Выгрузка переписок в Markdown через библиотеку |
| [`watch_new_messages.py`](watch_new_messages.py) | Опрос новых сообщений с сохранением курсора |
| [`search_messages.py`](search_messages.py) | Поиск по тексту сообщений во всех чатах |
| [`systemd/`](systemd/) | Юниты systemd для регулярной выгрузки |

Перед запуском выпустите токен:

```bash
retailcrm-mg bootstrap
python3 examples/export_transcripts.py
```
