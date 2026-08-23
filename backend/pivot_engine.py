import json
import os
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

def expand_niche_ideas_llm(user_input: str) -> list[dict]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []

    prompt = f"""
    The candidate entered: "{user_input}".
    1. Parse their discipline (e.g. Electronics, Computer Science, Mechanical).
    2. Parse their lifestyle preference:
       - If "desk", "remote", or "software": Suggest strictly digital, software, ASIC, FPGA, or R&D niches.
       - If "active", "field", or "travel": Suggest strictly physical/field niches (e.g. Marine ETO, Subsea ROV, Telemetry).
       - If unspecified: Suggest 2 digital and 2 physical niches.

    Brainstorm 4 uncrowded, high-leverage career paths.
    Return ONLY a valid JSON array of 4 objects with keys:
    - "niche_title": (Specific role name)
    - "rationale": (Why their technical skills qualify them)
    - "search_dork": (2-3 unquoted technical keywords, e.g. "ASIC Verification" or "ROV Pilot")
    """

    client = genai.Client(api_key=api_key)
    for model_name in ["gemini-2.5-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-2.0-flash"]:
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            raw = re.sub(r"^```json\s*|\s*```$", "", res.text.strip())
            return json.loads(raw)
        except Exception:
            continue
    return []