from fastapi import FastAPI

from .api.platform import router as platform_router

app = FastAPI(title="Workflow Helper API", version="0.3.0")


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(platform_router)
