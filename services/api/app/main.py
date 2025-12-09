from functools import lru_cache
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl


class Settings(BaseModel):
    default_timeout: float = 10.0
    user_agent: str = (
        "NexusWorkflowScraper/1.0 (+https://example.com/contact)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


class ScrapeRequest(BaseModel):
    url: HttpUrl


class ScrapeResponse(BaseModel):
    url: HttpUrl
    title: str | None
    meta_description: str | None


app = FastAPI(title="Workflow Helper API", version="0.1.0")


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_metadata(payload: ScrapeRequest) -> Any:
    settings = get_settings()
    headers = {"User-Agent": settings.user_agent}

    async with httpx.AsyncClient(
        timeout=settings.default_timeout, headers=headers
    ) as client:
        try:
            response = await client.get(str(payload.url))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag["content"].strip() if meta_desc_tag else None

    return ScrapeResponse(url=payload.url, title=title, meta_description=meta_description)
