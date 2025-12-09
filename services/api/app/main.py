from fastapi import FastAPI

from .api.routes import router as external_router

app = FastAPI(title="Workflow Helper API", version="0.2.0")


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(external_router)
