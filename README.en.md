<div align="center">

# RetailCRM MG Connector

**Pull customer conversations out of RetailCRM chats with one command.**

The connector issues its own `mgBot` token through the RetailCRM API and reads
channels, chats, dialogs and messages from MessageGateway. It works with any
RetailCRM account: you supply the addresses, nothing is hardcoded.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776ab.svg)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-success.svg)](pyproject.toml)

[Русская версия](README.md)

</div>

---

## Why

RetailCRM keeps customer conversations in MessageGateway (MG): WhatsApp, Telegram,
VK, Avito, e-mail. Reading them from outside requires an `mgBot` token, which the
admin UI never shows — RetailCRM issues it when you register an integration module.

This connector automates the whole chain:

```
RetailCRM API key  →  integration module  →  mgBot token  →  chats and messages
```

**Core rule:** one integration, one module, one token. Never copy a token from
another server — reissuing revokes the old one and breaks both integrations.

## Features

- **Token bootstrap** — registers an integration module and asks RetailCRM to issue
  a fresh token via `integrations[mgBot][refreshToken]`.
- **Conversation access** — channels, chats, dialogs, messages, customers and users,
  with `since_id` cursor pagination.
- **Export** — JSON, JSONL or human-readable Markdown transcripts.
- **Diagnostics** — `doctor` validates the whole chain and reports what broke.
- **Secure by default** — secrets are masked, `apiKey` is stripped from logged URLs,
  `.env` is written with `chmod 600`.
- **Zero dependencies** — Python 3.9+ standard library only.
- **Account-agnostic** — no built-in hostnames: cloud, self-hosted or custom domain.

## Quick start

```bash
git clone https://github.com/saniq7/RetailCRM-MG-Connector.git
cd RetailCRM-MG-Connector
pip install -e .

retailcrm-mg bootstrap --base-url https://crm.example.com   # your own CRM address
retailcrm-mg doctor
retailcrm-mg chats --limit 20
retailcrm-mg export --out ./export --format md
```

`https://crm.example.com` is a placeholder — use the address you log into.
A bare host works too: `crm.example.com` becomes `https://crm.example.com`.

You need a RetailCRM API key allowed to read and write integration modules
(`/api/integration-modules/{code}/edit`). It is required for `bootstrap` only.

The MessageGateway address is taken from the RetailCRM response. If your CRM
version does not return it, pass `--mg-api-base https://mg.example.com/api/bot/v1`.

## Commands

| Command | Description |
|---|---|
| `bootstrap` | Register the integration module, issue the `mgBot` token, save `.env` |
| `doctor` | Check config, RetailCRM key and MG access |
| `config` | Print the effective configuration with masked secrets |
| `modules` | List account integration modules |
| `channels` / `chats` / `dialogs` / `messages` | Read MG entities |
| `export` | Dump transcripts to `json`, `jsonl` or `md` |

Every listing command accepts `--json` for piping into `jq`.

## Library usage

```python
from retailcrm_mg import Config, MgClient
from retailcrm_mg.export import fetch_transcripts, to_markdown

config = Config.load()
client = MgClient(config.require_mg_api_base(), config.require_bot_token())

for transcript in fetch_transcripts(client, limit=5):
    print(to_markdown(transcript))
```

## Configuration

Precedence: `.env` → environment variables → CLI flags.
See [`.env.example`](.env.example) for the full list of variables.

There are no default addresses: `RETAILCRM_BASE_URL` and `RETAILCRM_MG_API_BASE`
belong to your account, and guessing them would be worse than asking.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

Tests run against a stubbed HTTP client — no network access required.

## Versioning

[Semantic versioning](https://semver.org/). `retailcrm_mg.__version__` is the single
source of truth; `vX.Y.Z` tags trigger the release workflow. See [CHANGELOG.md](CHANGELOG.md).

## Authors

- [@saniq7](https://github.com/saniq7)
- [@capelancrm](https://github.com/capelancrm)

## License

[MIT](LICENSE) © saniq7
