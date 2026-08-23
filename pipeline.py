import json
import os
import re
import subprocess
import time
from urllib.parse import urlparse
from backend.pivot_engine import expand_niche_ideas_llm

COLLECTOR_ID = "c_mt2zb7wq1kjlbklctz"

def bdata_exec(command: str):
    res = subprocess.run(
        f'npx -p @brightdata/cli bdata {command} --json',
        shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if res.returncode == 0 and res.stdout and res.stdout.strip():
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            return None
    return None

def trigger_auto_healing(collector_id: str, issue_desc: str) -> bool:
    print(f"\n[⚠️ REPAIR] Healing collector {collector_id}: {issue_desc}")
    heal_res = subprocess.run(
        f'npx -p @brightdata/cli bdata scraper heal {collector_id} "{issue_desc}"',
        shell=True, capture_output=True, text=True
    )
    if heal_res.returncode == 0:
        approve_res = subprocess.run(
            f'npx -p @brightdata/cli bdata scraper approve {collector_id}',
            shell=True, capture_output=True, text=True
        )
        return approve_res.returncode == 0
    return False

def validate_extraction(record: dict) -> tuple[bool, str]:
    if not record or not isinstance(record, dict) or "error" in record:
        return False, "Empty or broken response"
    if not (record.get("job_title") or record.get("title")):
        return False, "Missing job_title"
    if not record.get("description") or len(record["description"].strip()) < 30:
        return False, "Missing description"
    return True, "Valid"

def is_direct_posting(url: str) -> bool:
    if not url or not url.startswith("http") or "/apply" in url:
        return False
    if any(agg in url for agg in ["linkedin.com", "glassdoor.com", "indeed.com"]):
        return False
    return len([s for s in urlparse(url).path.split("/") if s]) >= 2

def clean_company(raw_name: str, url: str) -> str:
    if raw_name and raw_name.lower() not in ["direct company", "company", "direct ats", ""]:
        return raw_name.replace(" logo", "").replace(" Careers", "").strip()
    slugs = [p for p in urlparse(url).path.split("/") if p]
    return slugs[0].replace("-", " ").title() if slugs else "Direct Company"

def shorten_text(text: str, words_limit: int = 28) -> str:
    clean = re.sub(r'\s+', ' ', text or "").strip()
    words = clean.split()
    return " ".join(words[:words_limit]) + "..." if len(words) > words_limit else clean

def parse_work_type(location: str, desc: str) -> str:
    txt = f"{location} {desc}".lower()
    if "remote" in txt:
        return "Remote"
    if "hybrid" in txt:
        return "Hybrid"
    return "On-site"

def stream_niche_discovery(user_background: str):
    os.makedirs("data", exist_ok=True)
    pivots = expand_niche_ideas_llm(user_background)
    if not pivots:
        yield {"type": "done", "total": 0}
        return

    yield {
        "type": "niches_ready",
        "niches": [
            {
                "id": i,
                "title": p["niche_title"],
                "rationale": p.get("rationale", ""),
                "dork": p.get("search_dork", p["niche_title"])
            }
            for i, p in enumerate(pivots)
        ]
    }

    all_jobs = []

    for pivot in pivots:
        clean_terms = pivot.get("search_dork", pivot["niche_title"]).replace('"', '').strip()
        dork = f'(site:jobs.lever.co OR site:jobs.ashbyhq.com OR site:boards.greenhouse.io) {clean_terms} Apply'
        
        yield {"type": "searching_niche", "niche": pivot["niche_title"]}
        search_data = bdata_exec(f'search "{dork}"')
        
        target_urls = []
        if search_data:
            items = search_data.get("organic", []) if isinstance(search_data, dict) else search_data
            if isinstance(items, list):
                target_urls = [it.get("link") or it.get("url") for it in items if isinstance(it, dict) and is_direct_posting(it.get("link") or it.get("url"))]

        for url in target_urls[:1]:
            raw_res = bdata_exec(f'scraper run {COLLECTOR_ID} "{url}"') if "jobs.lever.co" in url else None
            record = raw_res[0] if isinstance(raw_res, list) and raw_res else (raw_res or {})
            
            is_valid, reason = validate_extraction(record)
            if not is_valid and "jobs.lever.co" in url:
                yield {"type": "log", "message": f"Repairing extraction for {url[:30]}..."}
                if trigger_auto_healing(COLLECTOR_ID, f"Extract title, company, location, description for {reason}"):
                    retry = bdata_exec(f'scraper run {COLLECTOR_ID} "{url}"')
                    record = retry[0] if isinstance(retry, list) and retry else (retry or {})

            title = record.get("job_title") or record.get("title") or pivot["niche_title"]
            company = clean_company(record.get("company_name", ""), url)
            loc = record.get("location") or "Flexible Location"
            desc = record.get("description") or ""

            job = {
                "job_title": title,
                "company_name": company,
                "location": loc,
                "work_type": parse_work_type(loc, desc),
                "description": shorten_text(desc, 28),
                "niche_category": pivot["niche_title"],
                "apply_url": record.get("apply_url") or url,
                "source_url": url
            }
            all_jobs.append(job)
            yield {"type": "job_found", "job": job}
            time.sleep(0.5)

    with open("data/jobs.json", "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2)

    yield {"type": "done", "total": len(all_jobs)}

def fetch_more_jobs(niche_title: str, search_dork: str, offset: int = 1, limit: int = 2) -> list[dict]:
    clean_terms = (search_dork or niche_title).replace('"', '').strip()
    dork = f'(site:jobs.lever.co OR site:jobs.ashbyhq.com OR site:boards.greenhouse.io) {clean_terms} Apply'
    search_data = bdata_exec(f'search "{dork}"')
    
    target_urls = []
    if search_data:
        items = search_data.get("organic", []) if isinstance(search_data, dict) else search_data
        if isinstance(items, list):
            target_urls = [it.get("link") or it.get("url") for it in items if isinstance(it, dict) and is_direct_posting(it.get("link") or it.get("url"))]

    more_jobs = []
    for url in target_urls[offset:offset+limit]:
        raw_res = bdata_exec(f'scraper run {COLLECTOR_ID} "{url}"') if "jobs.lever.co" in url else None
        record = raw_res[0] if isinstance(raw_res, list) and raw_res else (raw_res or {})
        
        loc = record.get("location") or "Flexible Location"
        desc = record.get("description") or ""

        more_jobs.append({
            "job_title": record.get("job_title") or record.get("title") or niche_title,
            "company_name": clean_company(record.get("company_name", ""), url),
            "location": loc,
            "work_type": parse_work_type(loc, desc),
            "description": shorten_text(desc, 28),
            "niche_category": niche_title,
            "apply_url": record.get("apply_url") or url,
            "source_url": url
        })
        time.sleep(0.5)

    return more_jobs

def run_niche_discovery(user_background: str) -> list[dict]:
    return [e["job"] for e in stream_niche_discovery(user_background) if e.get("type") == "job_found"]