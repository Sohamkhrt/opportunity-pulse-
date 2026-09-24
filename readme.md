# OpportunityPulse AI

Career background → four Gemini career pivots → Bright Data search → Scraper Studio job extraction → live SSE job cards.

## Run locally

Requires Python 3.11+ and Node.js 22+. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
npm ci
npm run build
.venv/Scripts/python -m backend.run
```

Before starting, add the settings from `.env.example` to your existing `.env`; do not overwrite existing credentials. On a fresh checkout copy `.env.example` to `.env`. Set `GEMINI_API_KEY`, `BRIGHTDATA_API_KEY`, a `BRIGHTDATA_SERP_ZONE` or `BRIGHTDATA_UNLOCKER_ZONE`, and a collector ID belonging to your Bright Data account. The previous application's Lever collector ID was `c_mt2zb7wq1kjlbklctz`; configure `BRIGHTDATA_COLLECTOR_ID` with it only if that collector is still available to your account.

The server serves both the built frontend and API. With no `PORT`, the OS picks a free port shown at startup. In the printed address, replace the bind host `0.0.0.0` with your machine's hostname to open it in a browser. Set `PORT` in `.env` if you want a stable port. Do not open the source HTML with `file://`. On macOS/Linux use `.venv/bin/python` in the commands above.

Rebuild with `npm run build` after changing frontend files. No provider keys are needed to compile the frontend or call `/healthz`; discovery reports a configuration error until credentials are configured.

## Recommended deployment: one Docker service on Render

This is the simplest route: one origin serves the page and streams, so no cross-origin setup is required.

1. Push this repository and create a Render Web Service using its Docker runtime, or import `render.yaml` as a Blueprint.
2. Set `GEMINI_API_KEY`, `BRIGHTDATA_API_KEY`, and `BRIGHTDATA_COLLECTOR_ID` and a search zone (`BRIGHTDATA_SERP_ZONE` or `BRIGHTDATA_UNLOCKER_ZONE`) as server environment variables. Keep `CORS_ORIGINS` empty for the unified deployment. Set `/healthz` as the health check.
3. Deploy and open the assigned HTTPS service URL. Render supplies `PORT`; the process binds to `HOST`, defaulting to `0.0.0.0`.

The Dockerfile compiles Tailwind and frontend assets, installs a locked Bright Data CLI during the build, and runs as a non-root user. It does not copy `.env` or cached job data. No persistent disk is required. For Docker outside Render, supply `PORT` and publish that same container port using your chosen host port; Docker does not infer published ports from environment variables.

[Render port binding documentation](https://render.com/docs/web-services#port-binding)

## Alternative: Vercel frontend + Render backend

1. Deploy the Docker backend on Render as above.
2. Import the same repository into Vercel with repository root as Root Directory and framework preset **Other**. The checked-in `vercel.json` uses `npm ci`, `npm run build`, and `dist` as output. Remove any old Python-function or routing overrides in the project dashboard.
3. Set Vercel's **build environment** variable `PUBLIC_API_BASE_URL` to the exact Render HTTPS origin, without a path. Redeploy after changing it. This is the only configuration written into the public `config.js` file; never put provider keys in Vercel frontend settings.
4. Set Render's `CORS_ORIGINS` to your exact Vercel HTTPS origin. Multiple trusted production/preview origins may be comma-separated. Restart/redeploy the backend after changes. Preview domains must be explicitly added.

The browser connects directly to Render for SSE and POST requests; there is no Vercel Python function or proxy timeout in the streaming path. A Vercel build fails with a clear message if its API origin is missing. The build script reads `PUBLIC_API_BASE_URL` from the process environment, not from the Python `.env` file. Outside Vercel, omitting it builds a same-origin frontend.

[Vercel build configuration](https://vercel.com/docs/project-configuration/vercel-json)

## Environment settings

| Setting | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Server-only Gemini credential. Required for discovery. |
| `BRIGHTDATA_API_KEY` | Server-only Bright Data credential. No interactive login needed. |
| `BRIGHTDATA_SERP_ZONE` / `BRIGHTDATA_UNLOCKER_ZONE` | Search zone name from your Bright Data account; set at least one. Local CLI settings are not copied into Docker. |
| `BRIGHTDATA_COLLECTOR_ID` | Scraper Studio collector trained for Lever pages. |
| `BRIGHTDATA_ASHBY_COLLECTOR_ID` | Optional collector trained for Ashby pages. |
| `BRIGHTDATA_GREENHOUSE_COLLECTOR_ID` | Optional collector trained for Greenhouse pages. |
| `GEMINI_MODEL` | Model accessible to your account; defaults to `gemini-3.5-flash-lite`. |
| `CORS_ORIGINS` | Exact permitted frontend origins; empty for same-origin use. |
| `HOST` / `PORT` | Bind interface and platform-assigned port. No fixed port in code. |
| `PUBLIC_API_BASE_URL` | Public frontend build-time API origin; empty for same-origin builds. |
| `PROVIDER_TIMEOUT_SECONDS` | Per Gemini/CLI operation timeout, default 120. |
| `DISCOVERY_TIMEOUT_SECONDS` | Overall discovery or more-jobs deadline, default 900. |
| `MAX_CONCURRENT_REQUESTS` | Maximum active expensive requests per process, default 2. |
| `BRIGHTDATA_AUTO_HEAL` | Default false. True enables collector repair, approval, and one retry. |

Only ATS hosts with configured collectors are searched. Each collector must return `job_title` (or `title`), `company_name`, `location`, `description`, and optionally `apply_url`. A title and description of at least 30 characters are required to display a listing. Configure Bright Data's search/SERP zones and credits for the account before use. Model and collector access cannot be inferred from the code.

Auto-heal is an explicit opt-in because it changes and approves a shared remote collector. If enabled with multiple concurrent users, those users share the changed collector; use one request at a time while testing repair. Disabling it does not disable normal search or extraction.

[Bright Data CLI authentication and commands](https://github.com/brightdata/cli)

## What was repaired

- Invalid JavaScript inside the Tailwind script tag prevented `BACKEND_URL` from being defined. Scripts and generated public configuration now have separate valid tags; Tailwind is compiled to local CSS.
- The saved `fetch` payload was already closed. Its surrounding pagination code was broken: it incremented the offset before fetching, skipped a result, overlapped later batches, and deleted `moreNicheLabel` with `innerText`. The server now returns a cursor; the browser preserves the label and advances only after successful responses.
- Vercel incorrectly tried to host a Python backend requiring Node and long-running scraping. Vercel now serves static output only; Render runs the streaming service.
- Wildcard CORS, fixed service URLs, dynamic CLI downloads, and shell-interpolated provider output were replaced with exact origin configuration, same-origin defaults, locked dependencies, and shell-free argument lists.
- Silent Gemini/CLI failures became visible, sanitized errors. SSE sends heartbeats, disables buffering, closes on errors, and cancels in-flight work when disconnected. Provider and overall deadlines bound requests.
- Unvalidated extraction previously produced plausible-looking fallback jobs. Incomplete records are now skipped with a notice, and each ATS uses its own configured collector.
- Raw provider strings were inserted into HTML and onclick attributes. Text now uses DOM text nodes, event listeners, and validated HTTPS application links.
- Every discovery overwrote a global relative JSON file, exposing one visitor's results to others and racing under concurrent requests. Results are now per browser session; `/api/jobs` remains a compatibility endpoint returning an empty list. Existing `data/jobs.json` is not served or modified.

## Verification

```powershell
.venv/Scripts/python -m pip install -r requirements-dev.txt
npm run build
.venv/Scripts/python -m pytest -q
npm test
```

Tests mock external providers, exercise real FastAPI routes and frontend DOM behavior, and cover pagination, validation, cancellation, CORS, error handling, and unsafe provider strings. They do not spend API credits. Run a real discovery after setting valid provider credentials and collectors to verify account-level access and extraction quality.

This remains an anonymous hackathon application. Concurrency limits bound simultaneous work but are not authentication or a spending limit. A larger public launch needs per-user abuse controls and provider budget limits. Search-result ordering can change between Find More requests; duplicate cards are suppressed, but pagination is best effort over the current first page of search results. Results are not durable across a page reload.
