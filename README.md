# Rivalens

Сервис мониторинга сайтов конкурентов с AI-суммаризацией изменений.
Домен: [rivalens.ru](https://rivalens.ru)

Каждые N часов сервис скачивает страницы конкурентов, сравнивает их с
предыдущими снапшотами (заголовки, ссылки, цены) и при изменениях
генерирует краткую сводку на русском через LLM.

## Стек

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (sync), Alembic, Postgres 16
- **Fetcher**: httpx + BeautifulSoup (lxml), без Playwright (VPS 2 GB RAM)
- **Scheduler**: APScheduler (AsyncIOScheduler в FastAPI lifespan)
- **LLM**: OpenAI-совместимый API (`AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL`)
- **Frontend**: Next.js 15 (App Router, TypeScript), Tailwind CSS v4
- **Infra**: Docker Compose, nginx (прод)

## Возможности

- JWT-аутентификация (register / login / me)
- CRUD конкурентов, автопривязка landing-страницы
- Ручной «Check now» и периодические проверки по расписанию
- Diff сущностей (заголовки / ссылки / цены) между снапшотами
- AI-insight по изменениям (при ошибке LLM пайплайн не падает)
- Тарифы: free = 1 конкурент, pro = 10, business = без лимита
  (переключение без оплаты, MVP)

## Быстрый старт (Docker)

```bash
cp .env.example .env          # заполнить AI_*, JWT_SECRET
docker compose up --build
```

- Frontend: http://localhost:3001
- Backend health: http://localhost:8001/health

## Локальная разработка (без Docker)

**Backend:**

```bash
cd backend
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8001
pytest
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Frontend ходит в backend через `NEXT_PUBLIC_API_URL`
(см. `frontend/src/lib/api.ts`).

## Тесты и проверки

- Backend: `pytest` (из `backend/`) — нужен локальный Docker
  (тесты поднимают throwaway Postgres через testcontainers)
- Frontend: `npm run build` (из `frontend/`)
- `package-lock.json` генерируется только в Linux-контейнере — см.
  «Lock file policy» в CLAUDE.md

## Деплой на VPS

Пошаговая инструкция: [deploy/README.md](deploy/README.md).

Кратко: `cp .env.prod.example .env.prod` → заполнить секреты →
`docker compose -f docker-compose.prod.yml up -d --build` → DNS →
certbot → включить HTTPS-блок в `deploy/nginx.conf`.

## Переменные окружения

| Переменная | Назначение | Пример |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | учётные данные БД | `rivalens` |
| `DATABASE_URL` | строка подключения (SQLAlchemy) | `postgresql+psycopg://rivalens:...@postgres:5432/rivalens` |
| `JWT_SECRET` | секрет для подписи JWT (`openssl rand -hex 32`) | — |
| `AI_BASE_URL` | base_url OpenAI-совместимого API | `http://host:4100/v1` |
| `AI_API_KEY` | ключ LLM | — |
| `AI_MODEL` | имя модели | — |
| `AI_PROVIDER` | провайдер (`openai`) | `openai` |
| `CHECK_INTERVAL_HOURS` | интервал периодических проверок | `6` |
| `NEXT_PUBLIC_API_URL` | публичный URL API для фронтенда | `https://rivalens.ru` |

## Структура

```
backend/
  app/
    api/        # роуты: auth, competitors, billing, admin, schemas
    auth/       # JWT: security, deps
    billing/    # лимиты тарифов
    db/         # engine, session, base
    diff/       # сравнение сущностей снапшотов
    fetcher/    # httpx-клиент, extractor, hasher
    llm/        # суммаризация через OpenAI-совместимый API
    models/     # SQLAlchemy-модели
    pipeline.py # fetch -> extract -> diff -> summarize
    scheduler.py
  alembic/      # миграции
  tests/
frontend/
  src/
    app/        # страницы: /, /login, /register, /billing, /competitors/[id]
    components/ # Header, AuthGate
    lib/        # api.ts (обёртка fetch), auth.ts (токен)
deploy/         # nginx.conf, гайд по деплою
```
