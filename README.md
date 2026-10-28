# Rivalens

Сервис мониторинга сайтов конкурентов с AI-суммаризацией изменений.
Домен: [rivalens.ru](https://rivalens.ru)

## Стек

- **Backend**: Python 3.11, FastAPI, Postgres
- **Frontend**: Next.js (App Router, TypeScript)
- **LLM**: OpenAI-совместимый API (base_url / key / model из env)
- **Infra**: Docker Compose
- **VPS**: 2 GB RAM / 1 CPU — тяжёлые инструменты (Playwright и т.п.) не используются

## Запуск

1. Скопировать env-файл и заполнить значения:

   ```bash
   cp .env.example .env
   ```

2. Поднять всё через Docker:

   ```bash
   docker compose up --build
   ```

3. Проверить:
   - Backend: http://localhost:8000/health → `{"status": "ok"}`
   - Frontend: http://localhost:3000

### Локальная разработка (без Docker)

**Backend:**

```bash
cd backend
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## Текущее состояние (CP0)

Только каркас: health-check на backend, заглавная страница на frontend,
docker-compose с postgres + backend + frontend. Без фич.

---

# План на следующие шаги (не реализовано)

## Архитектура

```
                        ┌─────────────┐
        cron / worker → │  Scheduler  │ → HTTP fetch (httpx) конкурентов
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │  Diff Engine│ → сравнение версий контента
                        └──────┬──────┘
                               │ изменение
                        ┌──────▼──────┐
     OpenAI-совместимый ←│   Summarizer│ → краткая сводка на русском
              API        └──────┬──────┘
                               │
                        ┌──────▼──────┐
        email / web UI ←│ Notifications│
                        └─────────────┘
```

- **API-слой** (FastAPI): CRUD конкурентов/страниц, просмотр истории
  изменений и сводок, управление расписанием проверок.
- **Worker**: фоновый процесс (или задача в том же процессе через APScheduler
  / простейший event-loop) — скачивает страницы конкурентов по расписанию,
  сравнивает с предыдущей версией, при изменении сохраняет diff и дергает
  Summarizer.
- **Fetcher**: только `httpx` (без Playwright — ограничение VPS).
- **Summarizer**: тонкий клиент OpenAI-совместимого API, промпт —
  «что изменилось у конкурента, по-русски, коротко».
- **Notifications** (позже): email (SMTP) и UI-уведомления.

## Схема БД (предложение)

```
competitors                     # компании-конкуренты
  id            UUID PK
  name          TEXT            -- «Конкурент А»
  created_at    TIMESTAMPTZ

pages                           # отслеживаемые страницы
  id            UUID PK
  competitor_id UUID FK → competitors
  url           TEXT
  title         TEXT            -- человекочитаемое имя страницы
  check_interval_minutes INT DEFAULT 60
  css_selector  TEXT NULL       -- опционально: следить за частью страницы
  is_active     BOOLEAN DEFAULT TRUE
  last_checked_at TIMESTAMPTZ NULL
  UNIQUE (competitor_id, url)

page_snapshots                  # версии контента
  id            UUID PK
  page_id       UUID FK → pages
  content_hash  TEXT            -- sha256 нормализованного текста
  content_text  TEXT            -- сырой/нормализованный контент
  fetched_at    TIMESTAMPTZ
  fetch_status  TEXT            -- ok | http_error | timeout | parse_error

changes                         # зафиксированные изменения
  id            UUID PK
  page_id       UUID FK → pages
  old_snapshot_id UUID FK → page_snapshots
  new_snapshot_id UUID FK → page_snapshots
  diff_summary  TEXT            -- сводка от LLM
  created_at    TIMESTAMPTZ

notifications_log               # позже: что и кому отправили
  id            UUID PK
  change_id     UUID FK → changes
  channel       TEXT            -- email
  sent_at       TIMESTAMPTZ
```

## Структура папок backend (цель)

```
backend/
  app/
    main.py            # FastAPI, роутер-монтаж
    config.py          # pydantic-settings, чтение env
    db.py              # engine, session factory
    models/            # SQLAlchemy-модели (competitors, pages, ...)
    schemas/           # pydantic-схемы API
    api/               # роуты: /competitors, /pages, /changes
    services/
      fetcher.py       # httpx: скачать страницу, нормализовать
      differ.py        # сравнение версий, diff
      summarizer.py    # LLM-клиент
      scheduler.py     # расписание проверок
    worker.py          # entrypoint воркера (если отдельным процессом)
  alembic/             # миграции
  tests/
```

## Порядок шагов

1. **CP1 — БД**: SQLAlchemy-модели + Alembic, config, подключение Postgres.
2. **CP2 — CRUD API**: competitors + pages, валидация, тесты.
3. **CP3 — Fetcher + snapshots**: httpx, нормализация текста, сохранение версий.
4. **CP4 — Diff + LLM**: определение изменений, сводки через OpenAI-совместимый API.
5. **CP5 — Scheduler**: периодические проверки (APScheduler или аналог).
6. **CP6 — Frontend UI**: список конкурентов, страницы, лента изменений, сводки.
7. **CP7 — Notifications**: email, настройки уведомлений.
8. **CP8 — Deploy на VPS**: reverse-proxy (Caddy/nginx), HTTPS на rivalens.ru.
