# Rivalens — правила для Claude Code

## Коммиты
- Сообщения коммитов — только на английском.
- **Без** `Co-Authored-By` в коммитах.
- **STOP перед** `git add -A` и `git push` — сначала показать, что будет закоммичено/отправлено.
- Без git init, коммитов и push, пока явно не попросили.

## Защищённые файлы
**STOP перед изменением** — ждать явного согласия:
- `package.json`, `package-lock.json`
- `pyproject.toml`
- `docker-compose.yml`
- миграции БД (`backend/alembic/**`)

## Проверки
- После изменений backend — запускать `pytest` (из `backend/`).
- После изменений frontend — запускать `npm run build` (из `frontend/`).
- Если проверка падает — **показать текст ошибки целиком**, не чинить наугад.
  Гипотезы и фиксы — только после того, как ошибка показана.

## Код
- Без `@ts-ignore` и `# type: ignore` — чинить типы, а не глушить.
- Не ставить новые зависимости без согласования.
- Backend и frontend не трогать в одной задаче: одна задача — один слой.

## Инфраструктура
- VPS: 2 GB RAM / 1 CPU — тяжёлые инструменты (Playwright и т.п.) не использовать.
- LLM — только через OpenAI-совместимый API (`base_url` / `key` / `model` из env).

## Architecture decisions
- HTTP: httpx.AsyncClient, timeout=10s, UA "Rivalens/0.1"
- HTML parser: beautifulsoup4 + lxml
- Entities: {title, headings (h1/h2 text), links ({href,text}), prices (regex \d[\d\s]*[₽$€])}
- Static HTML only, no Playwright (VPS 2GB)
- LLM: openai SDK AsyncOpenAI(base_url=AI_BASE_URL, api_key=AI_API_KEY, timeout=60), model=AI_MODEL, provider=AI_PROVIDER
- Diff: compare entities of two latest snapshots, changes = list of {kind, payload}
- Insights: one per competitor per run, period = [min(prev), max(new)]
- On LLM error: save snapshots + changes, skip insight, log, do not fail
- Async all the way (httpx + AsyncOpenAI), DB session sync (SQLAlchemy sync)
- No auth in CP3 (single implicit user = first row in users)
- API prefix /api/v1
- Frontend fetch through lib/api.ts wrapper, not raw fetch in components
- Manual "Check now" is synchronous (async endpoint, awaits pipeline)
- Tailwind CSS v4 for frontend styling (PostCSS plugin, no tailwind.config, no autoprefixer)
- Frontend talks to backend via NEXT_PUBLIC_API_URL
- Backend host port 8001 (8000 taken by BioPhysLab)
- Frontend host port 3001 (3000 taken by BioPhysLab)
- NEXT_PUBLIC_API_URL -> localhost:8001

## Lock file policy
- frontend/package-lock.json генерируется ТОЛЬКО в Linux-контейнере
  (node:22-alpine), никогда на Windows
- При обновлении зависимостей: docker run --rm -v ${PWD}:/app -w /app
  node:22-alpine npm install
- optionalDependencies содержат linux-musl бинарники явно — чтобы lock
  был валиден даже если случайно сгенерирован на Windows
