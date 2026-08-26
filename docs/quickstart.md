# Быстрый старт

## 1. Что нужно заранее

- Python 3.9 или новее.
- Адрес вашего аккаунта RetailCRM.
- API-ключ RetailCRM с правами на integration modules.
- Подключённый к аккаунту MessageGateway хотя бы с одним каналом.

### Какие адреса подставлять

В документации везде стоят заглушки `https://crm.example.com` и
`https://mg.example.com` — реальных адресов в коннекторе нет ни одного,
и подставлять их надо свои.

| Что | Где взять |
|---|---|
| Адрес RetailCRM | Строка браузера, когда вы работаете в CRM. Годится и голый хост: `crm.example.com` превратится в `https://crm.example.com`, лишний `/api/v5` в конце будет отрезан |
| Адрес MessageGateway | Обычно определяется автоматически при `bootstrap`. Если нет — смотрите *Настройки → Интеграция → Чаты* или спросите поддержку RetailCRM |

Это относится и к самостоятельным инсталляциям: коннектор одинаково работает
с облаком и со своим сервером, лишь бы отвечали `/api/v5` и Bot API.

### Как получить API-ключ

1. RetailCRM → **Настройки** → **Интеграция** → **Ключи доступа к API**.
2. Создайте ключ, выберите магазин (или «все»).
3. Выдайте права на раздел **Интеграционные модули** — чтение и запись.
   Именно они закрывают метод `/api/integration-modules/{code}/edit`.

Ключ нужен один раз — для выпуска `mgBot`-токена. Дальше коннектор работает
только с токеном.

## 2. Установка

```bash
git clone https://github.com/saniq7/RetailCRM-MG-Connector.git
cd RetailCRM-MG-Connector
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Проверка:

```bash
retailcrm-mg --version
```

Без установки тоже работает: `python3 -m retailcrm_mg --help` из каталога `src`.

## 3. Выпуск токена

```bash
retailcrm-mg bootstrap --base-url https://crm.example.com
```

Подставьте адрес своего аккаунта вместо заглушки. Ключ будет запрошен
интерактивно — он не попадёт ни в историю shell, ни в список процессов.
Если запускаете из скрипта, передавайте ключ через окружение, а не аргументом:

```bash
RETAILCRM_API_KEY="$(cat /run/secrets/retailcrm_key)" \
RETAILCRM_BASE_URL="https://crm.example.com" \
    retailcrm-mg bootstrap
```

Что произойдёт:

1. Проверка ключа через `GET /api/v5/reference/sites`.
2. Проверка прав через `GET /api/v5/credentials` (предупреждение, не блокировка).
3. Проверка, не занят ли `integrationModule.code` другой интеграцией.
4. `POST /api/v5/integration-modules/{code}/edit` с `integrations[mgBot][refreshToken]=true`.
5. Извлечение токена и, если он есть в ответе, адреса MessageGateway.
6. Запись в `~/.retailcrm-mg/.env` с правами `0600`.
7. Контрольный запрос `GET /channels` к MG с заголовком `X-Bot-Token`.

Если адрес MG в ответе не пришёл, коннектор всё равно сохранит токен — терять
его нельзя, повторный выпуск отзовёт выданный. Допишите адрес в `.env`:

```env
RETAILCRM_MG_API_BASE=https://mg.example.com/api/bot/v1
```

и проверьте связку командой `retailcrm-mg doctor`.

### Несколько интеграций на одном аккаунте

Каждой — свой код модуля и свой файл конфигурации:

```bash
retailcrm-mg bootstrap --module-code analytics_bot   --env-file ~/.mg/analytics.env
retailcrm-mg bootstrap --module-code support_copilot --env-file ~/.mg/support.env
```

Если запустить `bootstrap` для уже существующего модуля, коннектор остановится
и предупредит: перевыпуск отзовёт действующий токен. Осознанный перевыпуск —
флаг `--refresh`.

## 4. Проверка

```bash
retailcrm-mg doctor
```

```text
✅ Конфиг           /root/.retailcrm-mg/.env
✅ RetailCRM API    https://crm.example.com · ключ Xy7Kd2...9fQa
✅ MessageGateway   https://mg.example.com/api/bot/v1 · каналов 4 (активных 3)
```

Команда возвращает `0`, только если всё в порядке, — её удобно ставить
в healthcheck или в CI деплоя.

## 5. Чтение переписок

```bash
retailcrm-mg channels
retailcrm-mg chats --limit 20
retailcrm-mg chats --channel-id 42 --json | jq '.[].id'
retailcrm-mg messages --chat-id 12345
retailcrm-mg export --out ./export --format md --limit 100 --messages 500
```

## 6. Регулярная выгрузка

```cron
0 * * * * /opt/mg/.venv/bin/retailcrm-mg export --out /var/lib/mg/export --format jsonl >> /var/log/mg-export.log 2>&1
```

Пример unit-файла systemd — в [`examples/`](../examples/).
