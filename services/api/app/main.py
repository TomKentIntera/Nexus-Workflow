from fastapi import FastAPI

from .api.platform import router as platform_router
from .api.runs import router as runs_router
from .database import Base, engine

app = FastAPI(title="Workflow Helper API", version="0.4.0")


@app.on_event("startup")
def _create_schema() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(platform_router)
app.include_router(runs_router)
