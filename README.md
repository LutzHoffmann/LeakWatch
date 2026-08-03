# LeakWatch — Credential Leak Monitor

LeakWatch monitors paste sites, Telegram channels and public leak dumps for
your domains and email addresses, and alerts you the moment a credential
matching your monitored values shows up.

> **Status:** Phase 1 scaffold — core engine skeleton (watchers, LLM analyzer,
> matcher, alerter) plus a Next.js UI stub. Real watcher implementations and
> the full dashboard land in later phases.

## Why?

Every organisation with more than a handful of employees eventually faces
credential leaks in public paste archives and chat channels. LeakWatch is a
small, focused tool that watches those sources for you and raises an alert.

## Architecture

```mermaid
flowchart LR
    subgraph Sources[Sources]
        Pastebin[Pastebin]
        Gists[GitHub Gists]
        Telegram[Telegram channels]
    end

    subgraph Core[LeakWatch core]
        Watchers[Watchers async]
        Analyzer[Analyzer GLM-5.2]
        Matcher[Matcher pg]
        Alerter[Alerter mail/tg/webhook]
    end

    DB[(PostgreSQL + pgvector)]
    Redis[(Redis + ARQ)]
    UI[Web UI Next.js + shadcn]

    Pastebin --> Watchers
    Gists --> Watchers
    Telegram --> Watchers
    Watchers -->|RawItem| Analyzer
    Analyzer -->|Credential| Matcher
    Matcher -->|Match| Alerter
    Matcher --> DB
    Alerter --> DB
    Watchers --> DB
    Redis --- Core
    UI --- DB
```

### Core loop

```
Watcher polls source -> new text found?
  -> GLM-5.2 extracts emails, passwords, URLs, wallets
  -> Matcher checks against user domains/emails
  -> Match? -> Alert + persist
```

## Tech stack

| Layer        | Tech                          | Why                                    |
| ------------ | ----------------------------- | --------------------------------------- |
| Language     | Python 3.12+                  | #1 in security tooling                  |
| Async        | asyncio + httpx               | Modern Python patterns                  |
| Queue        | Redis + ARQ                   | Lighter than Celery, modern             |
| Database     | PostgreSQL + pgvector         | SQL + vector search                     |
| LLM          | GLM-5.2 via OpenRouter         | AI integration                          |
| Frontend     | Next.js + shadcn/ui           | React, professional look                 |
| Deployment   | Docker Compose + GitHub Actions CI | DevOps basics                    |
| Tests        | pytest + coverage >80%        | Engineering discipline                  |

## Quickstart

```bash
git clone <repo-url> leakwatch
cd leakwatch
cp backend/.env.example backend/.env   # fill in OPENROUTER_API_KEY etc.
docker compose up --build
```

The stack starts PostgreSQL (pgvector), Redis, the backend ARQ worker and the
Next.js frontend stub.

### Local development (backend)

```bash
cd backend
uv sync --extra dev
uv run pytest            # run tests with coverage gate
uv run leakwatch run-once # run a single watch cycle
uv run arq leakwatch.worker.WorkerSettings  # start the cron worker
```

### Local development (frontend)

```bash
cd frontend
npm install
npm run dev
```

## Configuration

All configuration is via environment variables (see
[`backend/.env.example`](backend/.env.example)). The most important ones:

| Variable                          | Purpose                              |
| --------------------------------- | ------------------------------------ |
| `DATABASE_URL`                    | Async SQLAlchemy Postgres URL        |
| `REDIS_URL`                       | Redis URL for ARQ                    |
| `OPENROUTER_API_KEY`              | OpenRouter API key (GLM-5.2)         |
| `LLM_MODEL`                       | OpenRouter model slug (default `z-ai/glm-5.2`) |
| `GITHUB_TOKEN`                    | GitHub token for the Gists watcher   |
| `RESEND_API_KEY` / `ALERT_TO_EMAIL` | Email alerts (Resend)              |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram alerts            |
| `ALERT_WEBHOOK_URL`               | Generic webhook (Slack/Teams ready)  |

## Roadmap

- **Phase 1 (4 weeks):** Core engine — watchers, GLM-5.2 analyzer, persistence.
- **Phase 2 (2-3 weeks):** Matching + alerting against user domains/emails.
- **Phase 3 (2-3 weeks):** Web UI — overview, search, settings, analytics, OAuth.

## Project layout

```
LeakWatch/
├── .github/workflows/ci.yml
├── docker-compose.yml
├── backend/        # Python (uv) core engine + ARQ worker
│   ├── pyproject.toml
│   ├── src/leakwatch/
│   └── tests/
└── frontend/       # Next.js + shadcn/ui dashboard
```

## Contributing

PRs welcome. Please open an issue first for larger changes. Run
`uv run ruff check` and `uv run pytest` before submitting.

## License

MIT
