"""Server-only configuration; never exported to the browser."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def cors_origins() -> list[str]:
    origins = [x.strip().rstrip("/") for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname
                or parsed.path or parsed.query or parsed.fragment or parsed.username or "*" in origin):
            raise ValueError("CORS_ORIGINS must contain exact HTTP(S) origins without paths or wildcards")
    return origins


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROVIDER_TIMEOUT = positive_int("PROVIDER_TIMEOUT_SECONDS", 120)
DISCOVERY_TIMEOUT = positive_int("DISCOVERY_TIMEOUT_SECONDS", 900)
MAX_CONCURRENT = positive_int("MAX_CONCURRENT_REQUESTS", 2)
AUTO_HEAL = os.getenv("BRIGHTDATA_AUTO_HEAL", "false").lower() == "true"
COLLECTORS = {
    host: os.getenv(variable, "").strip()
    for host, variable in {
        "jobs.lever.co": "BRIGHTDATA_COLLECTOR_ID",
        "jobs.ashbyhq.com": "BRIGHTDATA_ASHBY_COLLECTOR_ID",
        "boards.greenhouse.io": "BRIGHTDATA_GREENHOUSE_COLLECTOR_ID",
        "job-boards.greenhouse.io": "BRIGHTDATA_GREENHOUSE_COLLECTOR_ID",
    }.items()
}


class ProviderError(RuntimeError):
    """A sanitized error safe to show in the browser."""


def require_configuration() -> None:
    missing = [name for name in ("GEMINI_API_KEY", "BRIGHTDATA_API_KEY") if not os.getenv(name, "").strip()]
    if not any(COLLECTORS.values()):
        missing.append("BRIGHTDATA_COLLECTOR_ID (or an ATS-specific collector)")
    if missing:
        raise ProviderError("Server configuration missing: " + ", ".join(missing))
