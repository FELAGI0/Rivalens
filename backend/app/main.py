import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, competitors
from app.scheduler import start_scheduler, stop_scheduler

# uvicorn configures only its own uvicorn.* loggers: root stays at
# WARNING with no handlers, so app INFO logs vanish. Give the "app"
# logger a stderr handler so pipeline/scheduler events are visible.
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("%(levelname)s [%(name)s] %(message)s")
)
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
_app_logger.addHandler(_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Rivalens API", lifespan=lifespan)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(competitors.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
