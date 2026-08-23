# OpportunityPulse AI ⚡

> Autonomous Lateral Career Intelligence & Niche Arbitrage Scout built for the **WeMakeDevs × Bright Data: Into the Scrape-Verse Hackathon** (August 17–23, 2026).

---

## 🎯 The Problem & Our Approach

Traditional job boards force candidates into hyper-competitive, crowded keyword matches where thousands apply for standard software roles. **OpportunityPulse AI** performs career arbitrage: it uses Gemini LLM reasoning to identify high-leverage, uncrowded lateral career domains matching a candidate's core discipline and work-environment constraints (e.g., mapping Computer Engineering or Electronics into *Subsea ROV Controls, Avionics Telemetry, Offshore Wind SCADA, or Autonomous AgTech Integration*). It then scouts the open web in real time and extracts verified listings via Bright Data Scraper Studio.

---

## 🏗️ Architecture & Bright Data Integration

```text
[ User Background / Lifestyle Query ]
  │
  ▼
[ Gemini Lateral Pivot Engine ] ──► Synthesizes 4 unexpected career paths
  │
  ▼
[ Web Scout (bdata search) ] ────► Queries live ATS boards across Google/Bing SERP
  │
  ▼
[ Scraper Studio Collector ] ────► Extracts structured data via Collector c_mt2zb7wq1kjlbklctz
  │
  ▼
[ Quality Sentinel & Auto-Heal ] ─► Validates output; auto-heals & approves on failure
  │
  ▼
[ FastAPI SSE Stream Server ] ───► Emits live discovery logs & job cards one by one
  │
  ▼
[ Minimalist Dark-Mode UI ] ─────► Instant topic filtering & on-demand "Find More" scouting

```

### Scraper Studio Collector

* **Collector ID:** `c_mt2zb7wq1kjlbklctz`
* **Target Schema:** `job_title`, `company_name`, `location`, `description`, `apply_url`
* **Closed-Loop Self-Healing:** The pipeline detects empty/malformed records, triggers `bdata scraper heal` with the failure context, auto-approves the patch with `bdata scraper approve`, and re-extracts the listing dynamically.

---

## 📂 Repository Structure

```text
scrape-verse/
├── .env                  # GEMINI_API_KEY
├── pipeline.py           # Bright Data Search + Collector Runner + Quality Sentinel
├── readme.md             # Architecture documentation & setup guide
├── backend/
│   ├── main.py           # FastAPI SSE streaming service & on-demand routes
│   └── pivot_engine.py   # Gemini lateral reasoning & search term synthesizer
├── frontend/
│   └── index.html        # Clean dark-mode dashboard with real-time SSE feed
└── data/
    └── jobs.json         # Cached JSON dataset

```

---

## 🚀 Quickstart & Setup

### 1. Prerequisites & Environment

Ensure Node.js and Python 3.11+ are installed, then authenticate the Bright Data CLI and install backend dependencies:

```bash
npx -p @brightdata/cli bdata login
pip install fastapi uvicorn pydantic python-dotenv google-genai

```

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here

```

### 2. Start the Backend API

```bash
uvicorn backend.main:app --reload --port 8000

```

### 3. Launch the Frontend

Open `frontend/index.html` directly in any modern web browser.

---

## 🛡️ Autonomous Self-Healing Verification

If an ATS changes its markup structure or drops a selector, Scraper Studio repairs the extractor from the terminal or through our autonomous validation watchdog:

```bash
# 1. Trigger AI repair against a natural-language description
npx -p @brightdata/cli bdata scraper heal c_mt2zb7wq1kjlbklctz "The title and description selectors moved"

# 2. Approve and deploy the patched extractor schema
npx -p @brightdata/cli bdata scraper approve c_mt2zb7wq1kjlbklctz

```

Downstream API routes and frontend card layouts continue rendering without requiring manual code changes.