# Используемые методы API

## RetailCRM API v5

База: `${RETAILCRM_BASE_URL}/api/v5`, где `RETAILCRM_BASE_URL` — адрес вашего
аккаунта. Аутентификация: параметр `apiKey` в query.

| Метод | Назначение | Где используется |
|---|---|---|
| `GET /reference/sites` | Проверка живости ключа | `bootstrap`, `doctor` |
| `GET /credentials` | Список прав ключа | `bootstrap` (предупреждение) |
| `GET /integration-modules` | Список модулей аккаунта | `modules` |
| `GET /integration-modules/{code}` | Чтение конкретного модуля | `bootstrap` |
| `POST /integration-modules/{code}/edit` | Создание/обновление модуля и выпуск токена | `bootstrap` |

### Выпуск токена

Тело запроса — `application/x-www-form-urlencoded`:

| Поле | Значение |
|---|---|
| `integrationModule[code]` | код модуля, `[A-Za-z0-9_-]` |
| `integrationModule[integrationCode]` | обычно совпадает с `code` |
| `integrationModule[clientId]` | уникальный идентификатор клиента интеграции |
| `integrationModule[name]` | отображаемое имя |
| `integrationModule[active]` | `true` |
| `integrationModule[integrations][mgBot][refreshToken]` | `true` — выпустить новый токен |

Успешный ответ содержит токен и иногда адрес MessageGateway; типичное расположение:

```json
{
  "success": true,
  "info": {
    "mgBot": {
      "token": "…",
      "endpointUrl": "https://mg.example.com"
    }
  }
}
```

Встречаются и другие варианты (`integrationModule.integrations.mgBot.token`),
поэтому коннектор ищет токен по нескольким известным путям и, в крайнем случае,
обходом дерева ответа. Так же ищется и `endpointUrl`: если он есть, адрес MG
подставляется автоматически, если нет — его указывает пользователь.

### Требуемые права ключа

Минимум — раздел «Интеграционные модули», чтение и запись:

```
/api/integration-modules
/api/integration-modules/{code}
/api/integration-modules/{code}/edit
```

## MessageGateway Bot API

База: `${RETAILCRM_MG_API_BASE}` — свой у каждого аккаунта, значения по умолчанию нет.
Путь Bot API внутри неё стандартный: `/api/bot/v1`, коннектор допишет его сам,
если указан только хост. Аутентификация: заголовок `X-Bot-Token`.

| Метод | Возвращает | Команда |
|---|---|---|
| `GET /channels` | Подключённые каналы | `channels` |
| `GET /chats` | Чаты; фильтр `channel_id` | `chats` |
| `GET /dialogs` | Диалоги; фильтр `chat_id` | `dialogs` |
| `GET /messages` | Сообщения; фильтры `chat_id`, `dialog_id`, `channel_id` | `messages`, `export` |
| `GET /members` | Участники чатов | библиотека |
| `GET /customers` | Клиенты | библиотека |
| `GET /users` | Операторы | библиотека |

### Пагинация

Общие параметры всех листингов:

| Параметр | Смысл |
|---|---|
| `limit` | размер страницы, максимум `100` |
| `since_id` | идентификатор, с которого продолжить обход |

Ответ — JSON-массив. Пустой массив или страница короче `limit` означают конец выборки.

### Пример сообщения

```json
{
  "id": 918273,
  "time": "2026-08-20T10:01:00Z",
  "type": "text",
  "scope": "public",
  "chat_id": 12345,
  "from": { "id": 55, "type": "customer", "name": "Иван" },
  "content": "Здравствуйте, где мой заказ?"
}
```

`normalize_message()` приводит это к виду:

```json
{
  "id": 918273,
  "time": "2026-08-20T10:01:00Z",
  "type": "text",
  "scope": "public",
  "direction": "in",
  "author": "Иван",
  "author_type": "customer",
  "text": "Здравствуйте, где мой заказ?",
  "attachments": []
}
```

Направление определяется по `from.type`: `customer` — входящее (`in`),
всё остальное (оператор, бот, система) — исходящее (`out`).

## Ссылки

- [Документация RetailCRM API](https://docs.retailcrm.ru/Developers/API)
- [Документация MessageGateway](https://docs.retailcrm.ru/Developers/modules/MG)
