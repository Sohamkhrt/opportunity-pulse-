import sys
import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from pipeline import stream_niche_discovery, fetch_more_jobs

app = FastAPI(title="OpportunityPulse API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class MoreJobsPayload(BaseModel):
    niche_title: str
    search_dork: Optional[str] = ""
    offset: int = 1
    limit: int = 2

@app.get("/api/jobs")
def get_jobs():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.json")
    if os.path.exists(data_path):
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

@app.get("/api/stream-discover")
def stream_discover(query: str = "computer engineer active"):
    def event_stream():
        for event in stream_niche_discovery(query):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/more-jobs")
def get_more_jobs(payload: MoreJobsPayload):
    new_jobs = fetch_more_jobs(
        niche_title=payload.niche_title,
        search_dork=payload.search_dork,
        offset=payload.offset,
        limit=payload.limit
    )
    return {"status": "success", "jobs": new_jobs}