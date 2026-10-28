from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import competitors


app = FastAPI(title="Rivalens API")

app.include_router(competitors.router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
