"""Cancelable Gemini -> Bright Data search -> Scraper Studio pipeline."""
import asyncio
import json
import os
import re
import shutil
from urllib.parse import urlsplit, urlunsplit
from backend.config import AUTO_HEAL, COLLECTORS, PROVIDER_TIMEOUT, ROOT, ProviderError
from backend.pivot_engine import expand_niche_ideas_llm


async def bdata_exec(*arguments: str):
    # Direct Node invocation also works on Windows, without a shell or npx prompts.
    entry = ROOT / "node_modules" / "@brightdata" / "cli" / "dist" / "index.js"
    node = shutil.which("node")
    if not node or not entry.is_file():
        raise ProviderError("Bright Data CLI is not installed. Run npm ci on the server.")
    env = {**os.environ, "CI": "true", "NO_COLOR": "1"}
    process = await asyncio.create_subprocess_exec(
        node, str(entry), *arguments, "--json", stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=PROVIDER_TIMEOUT)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
        raise
    if process.returncode:
        raise ProviderError("Bright Data request failed. Check server credentials, collector, zones and quota.")
    try:
        result = json.loads(stdout)
        if isinstance(result, dict) and result.get("error"):
            raise ValueError("Provider error")
        return result
    except (ValueError, UnicodeDecodeError):
        raise ProviderError("Bright Data returned an invalid response.") from None


def posting_url(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme != "https" or parts.hostname not in COLLECTORS
                or not COLLECTORS[parts.hostname] or parts.username or parts.password
                or parts.port not in (None, 443)):
            return None
        segments = [x for x in parts.path.split("/") if x]
        if len(segments) < 2:
            return None
        path = parts.path.rstrip("/").removesuffix("/apply")
        return urlunsplit(("https", parts.hostname, path, "", ""))
    except ValueError:
        return None


async def search_urls(terms: str) -> list[str]:
    sites = " OR ".join(f"site:{host}" for host, collector in COLLECTORS.items() if collector)
    clean_terms = re.sub(r"[^\w\s+-]", " ", terms).strip()
    result = await bdata_exec("search", f"({sites}) {clean_terms} Apply")
    items = result.get("organic", []) if isinstance(result, dict) else result
    if not isinstance(items, list):
        raise ProviderError("Bright Data search returned an unexpected format.")
    urls = [posting_url(item.get("link") or item.get("url")) for item in items if isinstance(item, dict)]
    return list(dict.fromkeys(url for url in urls if url))


def first_record(result) -> dict:
    if isinstance(result, list):
        result = result[0] if result else {}
    return result if isinstance(result, dict) else {}


def validate_extraction(record: dict) -> tuple[bool, str]:
    if record.get("error"):
        return False, "Collector returned an error"
    title = record.get("job_title") or record.get("title")
    if not isinstance(title, str) or not title.strip():
        return False, "Missing job title"
    description = record.get("description")
    if not isinstance(description, str) or len(description.strip()) < 30:
        return False, "Missing description"
    return True, "Valid"


async def extract_job(url: str, niche: str) -> dict | None:
    collector = COLLECTORS[urlsplit(url).hostname]
    record = first_record(await bdata_exec("scraper", "run", collector, url))
    valid, reason = validate_extraction(record)
    if not valid and AUTO_HEAL:
        await bdata_exec("scraper", "heal", collector,
                         f"Extract job_title, company_name, location, description and apply_url. {reason}.")
        await bdata_exec("scraper", "approve", collector)
        record = first_record(await bdata_exec("scraper", "run", collector, url))
        valid, _ = validate_extraction(record)
    if not valid:
        return None
    company = record.get("company_name") or record.get("company")
    if not isinstance(company, str) or not company.strip():
        company = urlsplit(url).path.split("/")[1].replace("-", " ").title()
    location = record.get("location")
    location = location if isinstance(location, str) and location.strip() else "Location not listed"
    description = re.sub(r"\s+", " ", record["description"]).strip()
    work_text = f"{location} {description}".lower()
    words = description.split()
    return {
        "job_title": (record.get("job_title") or record["title"]).strip(),
        "company_name": company, "location": location,
        "work_type": "Hybrid" if "hybrid" in work_text else "Remote" if "remote" in work_text else "On-site",
        "description": " ".join(words[:28]) + ("..." if len(words) > 28 else ""),
        "niche_category": niche,
        "apply_url": posting_url(record.get("apply_url")) or url, "source_url": url,
    }


async def fetch_more_jobs(niche_title: str, search_dork: str, offset: int = 0, limit: int = 2) -> dict:
    urls = await search_urls(search_dork or niche_title)
    selected = urls[offset:offset + limit]
    jobs, warnings = [], []
    for url in selected:
        try:
            job = await extract_job(url, niche_title)
            if job:
                jobs.append(job)
            else:
                warnings.append("A listing was skipped because its extracted title or description was incomplete.")
        except (ProviderError, TimeoutError):
            warnings.append("A listing could not be extracted. Check the collector or try again later.")
    next_offset = offset + len(selected)
    return {"jobs": jobs, "next_offset": next_offset, "has_more": next_offset < len(urls), "warnings": warnings}


async def stream_niche_discovery(user_background: str):
    pivots = await expand_niche_ideas_llm(user_background)
    yield {"type": "niches_ready", "niches": [
        {"id": i, "title": p["niche_title"], "rationale": p["rationale"], "dork": p["search_dork"]}
        for i, p in enumerate(pivots)
    ]}
    total = 0
    for pivot in pivots:
        niche = pivot["niche_title"]
        yield {"type": "searching_niche", "niche": niche}
        result = await fetch_more_jobs(niche, pivot["search_dork"], offset=0, limit=1)
        for warning in result["warnings"]:
            yield {"type": "log", "message": warning}
        for job in result["jobs"]:
            total += 1
            yield {"type": "job_found", "job": job}
        yield {"type": "niche_progress", "niche": niche,
               "next_offset": result["next_offset"], "has_more": result["has_more"]}
    yield {"type": "done", "total": total}
