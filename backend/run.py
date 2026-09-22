"""Start from the repository root with: python -m backend.run."""
import os
import uvicorn
from backend.config import positive_int

if __name__ == "__main__":
    # Port 0 asks the OS for a free port locally. Render supplies PORT explicitly.
    raw_port = os.getenv("PORT", "").strip()
    port = positive_int("PORT", 0) if raw_port else 0
    if port > 65535:
        raise ValueError("PORT must be at most 65535")
    uvicorn.run("backend.main:app", host=os.getenv("HOST", "0.0.0.0"), port=port, access_log=False)
