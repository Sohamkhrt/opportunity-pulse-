import asyncio
import contextlib
import json
import logging
import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from backend.config import (
    DISCOVERY_TIMEOUT, MAX_CONCURRENT, ROOT, ProviderError, cors_origins, require_configuration,
)
from pipeline import stream_niche_discovery, fetch_more_jobs

app = FastAPI(title="OpportunityPulse API")
app.add_middleware(
    CORSMiddleware, allow_origins=cors_origins(), allow_credentials=False,
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
slots = asyncio.Semaphore(MAX_CONCURRENT)
logger = logging.getLogger(__name__)
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class MoreJobsPayload(BaseModel):
    niche_title: ShortText
    search_dork: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    offset: int = Field(default=0, ge=0, le=1000)
    limit: int = Field(default=2, ge=1, le=5)


def check_configuration():
    try:
        require_configuration()
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


async def acquire_slot():
    if slots.locked():
        raise HTTPException(status_code=429, detail="Server is busy. Please retry shortly.", headers={"Retry-After": "15"})
    await slots.acquire()


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/api/jobs")
async def get_jobs():
    # No shared cache: never return a different visitor's discovery results.
    return []


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/api/stream-discover")
async def stream_discover(query: Annotated[str, Query(min_length=1, max_length=2000)]):
    if not query.strip():
        raise HTTPException(status_code=422, detail="Enter a background to discover careers.")

    async def event_stream():
        acquired = False
        pending = None
        iterator = None
        try:
            # Errors are data events because EventSource cannot read HTTP error bodies.
            require_configuration()
            await acquire_slot()
            acquired = True
            yield ": connected\n\n"
            iterator = stream_niche_discovery(query.strip())
            async with asyncio.timeout(DISCOVERY_TIMEOUT):
                while True:
                    pending = asyncio.create_task(anext(iterator))
                    while not pending.done():
                        done, _ = await asyncio.wait({pending}, timeout=10)
                        if not done:
                            yield ": heartbeat\n\n"
                    try:
                        event = pending.result()
                    except StopAsyncIteration:
                        break
                    yield sse(event)
        except ProviderError as exc:
            yield sse({"type": "error", "message": str(exc)})
        except HTTPException as exc:
            yield sse({"type": "error", "message": exc.detail})
        except TimeoutError:
            yield sse({"type": "error", "message": "Discovery timed out. Please retry with a narrower background."})
        except Exception as exc:
            # Provider exceptions can embed keys/URLs; log only their type.
            logger.error("Discovery failed (%s)", type(exc).__name__)
            yield sse({"type": "error", "message": "Discovery failed. Please try again."})
        finally:
            if pending is not None:
                pending.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pending
            if iterator is not None:
                await iterator.aclose()
            if acquired:
                slots.release()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-store, no-transform", "X-Accel-Buffering": "no",
    })


@app.post("/api/more-jobs")
async def get_more_jobs(payload: MoreJobsPayload):
    check_configuration()
    await acquire_slot()
    try:
        async with asyncio.timeout(DISCOVERY_TIMEOUT):
            return {"status": "success", **await fetch_more_jobs(**payload.model_dump())}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Scraping timed out. Please retry.") from None
    finally:
        slots.release()


# A single origin is the simplest local and Docker deployment. Vercel uses the same dist files.
if (ROOT / "dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
