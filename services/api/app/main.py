from __future__ import annotations

import os
import threading
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from .api.autotag import router as autotag_router
from .api.allowed_search_tags import router as allowed_search_tags_router
from .api.banned_tags import router as banned_tags_router
from .api.links import router as links_router
from .api.platform import router as platform_router
from .api.runs import router as runs_router
from .api.stats import router as stats_router
from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import Run, RunStatus

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


def _lease_reaper_loop() -> None:
    """Periodically clear expired run leases."""
    interval = int(os.environ.get("WF_LEASE_REAPER_INTERVAL_SECONDS", "60"))
    while True:
        try:
            now = datetime.utcnow()
            with SessionLocal() as session:
                # If a generator crashes mid-run, re-queue once the lease expires.
                session.execute(
                    update(Run)
                    .where(
                        Run.leased_until.is_not(None),
                        Run.leased_until < now,
                        Run.status == RunStatus.GENERATING,
                    )
                    .values(leased_until=None, status=RunStatus.QUEUED, updated_at=now)
                )

                # Clear any other expired leases without touching status.
                session.execute(
                    update(Run)
                    .where(
                        Run.leased_until.is_not(None),
                        Run.leased_until < now,
                        Run.status != RunStatus.GENERATING,
                    )
                    .values(leased_until=None, updated_at=now)
                )
                session.commit()
        except Exception:
            # Avoid crashing the API process due to lease cleanup failures.
            pass

        time.sleep(max(interval, 5))


@app.on_event("startup")
def _create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    t = threading.Thread(target=_lease_reaper_loop, name="lease-reaper", daemon=True)
    t.start()


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(platform_router)
app.include_router(runs_router)
app.include_router(autotag_router)
app.include_router(allowed_search_tags_router)
app.include_router(banned_tags_router)
app.include_router(links_router)
app.include_router(stats_router)
