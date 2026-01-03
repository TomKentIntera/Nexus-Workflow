from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.autotag import router as autotag_router
from .api.links import router as links_router
from .api.platform import router as platform_router
from .api.runs import router as runs_router
from .config import get_settings
from .database import Base, engine

app = FastAPI(title="Workflow Helper API", version="0.4.0")

settings = get_settings()
_origins = [o.strip() for o in (settings.cors_allow_origins or "*").split(",") if o.strip()]
if not _origins:
    _origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _create_schema() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(platform_router)
app.include_router(runs_router)
app.include_router(autotag_router)
app.include_router(links_router)
