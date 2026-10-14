"""FastAPI app: POST /api/check streams pipeline progress as Server-Sent Events."""
import hashlib
import json
import logging
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .llm import LLMError
from .pipeline import Pipeline

STATIC = config.ROOT / "static"
log = logging.getLogger("claimcheck")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        app.state.pipeline = Pipeline(client)
        yield


app = FastAPI(title="ClaimCheck", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Results are cached so repeated checks of the same message (demo examples, judges) cost nothing.
_cache: OrderedDict[str, dict] = OrderedDict()
_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _rate_limited(ip: str) -> bool:
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_HOUR:
        return True
    q.append(now)
    return False


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "models": config.MODELS}


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

    key = hashlib.sha256(" ".join(text.lower().split()).encode() + (img or b"")).hexdigest()
    cached = _cache.get(key)
    if cached is None and _rate_limited(_client_ip(request)):
        raise HTTPException(429, "Too many checks from your network. Please try again in an hour.")

    async def stream():
        if cached is not None:
            _cache.move_to_end(key)
            yield _sse({**cached, "cached": True})
            return
        try:
            async for event in request.app.state.pipeline.run(text, img, mime or "image/png"):
                if event["type"] == "result":
                    _cache[key] = event
                    while len(_cache) > config.CACHE_SIZE:
                        _cache.popitem(last=False)
                yield _sse(event)
        except (LLMError, httpx.HTTPError, ValueError) as e:
            log.exception("check failed: %s", e)
            yield _sse({"type": "error", "message": "Something went wrong while checking. Please try again."})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
