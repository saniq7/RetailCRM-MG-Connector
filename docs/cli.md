# Справочник CLI

```
retailcrm-mg [общие флаги] <команда> [флаги команды]
```

## Общие флаги

| Флаг | Смысл |
|---|---|
| `--env-file PATH` | Путь к `.env` (по умолчанию `~/.retailcrm-mg/.env`) |
| `--base-url URL` | Адрес вашего аккаунта RetailCRM |
| `--mg-api-base URL` | База MG Bot API вашего аккаунта |
| `-v`, `--verbose` | Подробные логи в stderr |
| `--version` | Версия коннектора |

Первые три работают в любой позиции — и до подкоманды, и после:

```bash
retailcrm-mg --base-url crm.example.com chats
retailcrm-mg chats --base-url crm.example.com
```

Адреса нормализуются: схема `https://` добавляется, если её нет; хвост `/api/v5`
у адреса CRM отрезается; путь `/api/bot/v1` у адреса MG дописывается.
Значений по умолчанию нет — команда, которой адрес нужен, скажет об этом явно
и завершится с кодом `2`.

## Коды возврата

| Код | Значение |
|---|---|
| `0` | Успех |
| `1` | Ошибка выполнения: сеть, API, отозванный токен |
| `2` | Проблема конфигурации или отказ от опасного действия |
| `130` | Прервано пользователем |

---

## bootstrap

Регистрирует integration module и выпускает `mgBot`-токен.

```bash
retailcrm-mg bootstrap [--api-key KEY] [--module-code CODE] [--module-name NAME]
                       [--client-id ID] [--refresh] [--force] [--no-write]
                       [--dump-response] [--ask-key]
```

| Флаг | Смысл |
|---|---|
| `--api-key` | API-ключ RetailCRM. Без него ключ спросят интерактивно |
| `--ask-key` | Всегда спрашивать ключ, даже если он есть в `.env` |
| `--module-code` | `integrationModule.code`; по умолчанию `mg_connector_<hostname>` |
| `--module-name` | Отображаемое имя модуля |
| `--client-id` | `integrationModule.clientId` |
| `--refresh` | Перевыпустить токен существующего модуля (старый будет отозван) |
| `--force` | Пропустить проверку существующего модуля |
| `--no-write` | Не писать `.env` — токен только показать замаскированным |
| `--dump-response` | Показать разбор ответа RetailCRM: пути к найденным токенам |

Возвращает `2`, если модуль уже привязан к MG и перевыпуск не подтверждён,
и `1`, если токен выпущен и сохранён, но адрес MessageGateway остался неизвестен.

## doctor

Проверяет конфигурацию, ключ RetailCRM и доступ к MG.

```bash
retailcrm-mg doctor [--api-key KEY]
```

Ненулевой код возврата при любой проблеме — годится для healthcheck.

## config

Печатает эффективную конфигурацию в JSON. Секреты замаскированы.

```bash
retailcrm-mg config
```

## modules

Список integration modules аккаунта — проверить, какие коды заняты.

```bash
retailcrm-mg modules [--api-key KEY] [--json]
```

## channels

```bash
retailcrm-mg channels [--limit N] [--json]
```

## chats

```bash
retailcrm-mg chats [--channel-id ID] [--limit N] [--json]
```

## dialogs

```bash
retailcrm-mg dialogs [--chat-id ID] [--limit N] [--json]
```

## messages

```bash
retailcrm-mg messages [--chat-id ID] [--dialog-id ID] [--channel-id ID] [--limit N] [--json]
```

## export

Выгружает переписки в файлы.

```bash
retailcrm-mg export [--out DIR] [--format json|jsonl|md]
                    [--channel-id ID] [--limit N] [--messages N]
```

| Флаг | Смысл | По умолчанию |
|---|---|---|
| `--out` | Каталог назначения | `./export` |
| `--format` | `json` — файл на чат, `jsonl` — один файл, `md` — читаемый транскрипт | `json` |
| `--channel-id` | Только чаты одного канала | все |
| `--limit` | Сколько чатов выгрузить | `20` |
| `--messages` | Максимум сообщений на чат | без ограничения |

---

## Рецепты

Идентификаторы всех активных каналов:

```bash
retailcrm-mg channels --json | jq '.[] | select(.activated_at) | .id'
```

Последние сообщения по каждому чату конкретного канала:

```bash
for id in $(retailcrm-mg chats --channel-id 42 --json | jq '.[].id'); do
  retailcrm-mg messages --chat-id "$id" --limit 5
done
```

Ежечасная инкрементальная выгрузка в JSONL:

```bash
retailcrm-mg export --out /var/lib/mg/export --format jsonl --limit 500
```

Проверка перед деплоем:

```bash
retailcrm-mg doctor || exit 1
```
