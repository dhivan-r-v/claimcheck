"""FastAPI app: POST /api/check streams pipeline progress as Server-Sent Events."""
import json
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, telegram
from .llm import LLMError
from .pipeline import Pipeline
from .store import cache_key, limiter, results

STATIC = config.ROOT / "static"
log = logging.getLogger("claimcheck")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        app.state.http = client
        app.state.pipeline = Pipeline(client)
        await telegram.register_webhook(client)
        yield


app = FastAPI(title="ClaimCheck", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(telegram.router)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "models": config.MODELS, "telegram": telegram.enabled()}


@app.post("/api/check")
async def check(request: Request, text: str = Form(""), image: UploadFile | None = File(None)):
    text = text.strip()
    if len(text) > config.MAX_TEXT_CHARS:
        raise HTTPException(413, f"Message too long (max {config.MAX_TEXT_CHARS} characters).")
    img = mime = None
    if image is not None and image.filename:
        mime = image.content_type or ""
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(415, "Image must be PNG, JPEG or WebP.")
        img = await image.read()
        if len(img) > config.MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image too large (max 5 MB).")
    if not text and not img:
        raise HTTPException(400, "Paste a message or attach a screenshot.")

    key = cache_key(text, img)
    cached = results.get(key)
    if cached is None and limiter.limited(f"ip:{_client_ip(request)}"):
        raise HTTPException(429, "Too many checks from your network. Please try again in an hour.")

    async def stream():
        if cached is not None:
            yield _sse({**cached, "cached": True})
            return
        try:
            async for event in request.app.state.pipeline.run(text, img, mime or "image/png"):
                if event["type"] == "result":
                    results.put(key, event)
                yield _sse(event)
        except (LLMError, httpx.HTTPError, ValueError) as e:
            log.exception("check failed: %s", e)
            yield _sse({"type": "error", "message": "Something went wrong while checking. Please try again."})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
