'use strict';
const apiBase = (window.APP_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');
const $ = id => document.getElementById(id);
let allJobs = [];
let discoveredNiches = [];
let activeFilter = null;
let progress = new Map();
let stream = null;
let busy = false;
let loadingMore = false;
let hadWarnings = false;

function notice(message) { $('notice').textContent = message; }
function element(tag, className, text) {
  const el = document.createElement(tag);
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function safeLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
function addJobs(jobs) {
  for (const job of jobs) {
    if (!allJobs.some(existing => existing.source_url === job.source_url && existing.niche_category === job.niche_category)) {
      allJobs.push(job);
    }
  }
}
function finish() {
  stream?.close();
  stream = null;
  busy = false;
  $('searchBtn').disabled = false;
  $('searchBtn').textContent = 'Discover Niches';
  $('searchingCard').classList.add('hidden');
  renderFilteredJobs();
  updateMore();
}
function startDiscovery() {
  if (busy || loadingMore) return;
  const query = $('queryInput').value.trim();
  if (!query) { notice('Enter your background and work preference first.'); return; }
  allJobs = [];
  discoveredNiches = [];
  progress = new Map();
  activeFilter = null;
  hadWarnings = false;
  busy = true;
  notice('');
  $('searchBtn').disabled = true;
  $('searchBtn').textContent = 'Discovering...';
  $('nichesBox').classList.add('hidden');
  $('showAllBtn').classList.add('hidden');
  $('nichesList').replaceChildren();
  $('jobsList').replaceChildren();
  $('findMoreContainer').classList.add('hidden');
  $('searchingCard').classList.remove('hidden');
  $('searchingStatus').textContent = 'Reasoning about lateral career pivots...';
  try {
    stream = new EventSource(`${apiBase}/api/stream-discover?query=${encodeURIComponent(query)}`);
    stream.onmessage = event => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'niches_ready':
            discoveredNiches = data.niches;
            $('nichesBox').classList.remove('hidden');
            renderNicheCards();
            break;
          case 'searching_niche':
            $('searchingStatus').textContent = `Scouting postings for: ${data.niche}...`;
            break;
          case 'job_found': addJobs([data.job]); renderFilteredJobs(); break;
          case 'niche_progress': progress.set(data.niche, data); break;
          case 'log': hadWarnings = true; notice(data.message); break;
          case 'error': notice(data.message); finish(); break;
          case 'done':
            finish();
            notice(`${allJobs.length} listing${allJobs.length === 1 ? '' : 's'} found.${hadWarnings ? ' Some listings could not be extracted.' : ''}`);
            break;
        }
      } catch {
        notice('The server returned an unreadable response. Please retry.');
        finish();
      }
    };
    stream.onerror = () => {
      notice('Connection interrupted. Check the backend URL, CORS configuration or service status, then retry.');
      finish(); // Close explicitly: automatic SSE reconnects would start paid work again.
    };
  } catch {
    notice('Unable to connect to the discovery service.');
    finish();
  }
}
function selectNicheFilter(title) {
  activeFilter = title;
  $('showAllBtn').classList.toggle('hidden', activeFilter === null);
  renderNicheCards();
  renderFilteredJobs();
  updateMore();
}
function renderNicheCards() {
  $('nichesList').replaceChildren();
  for (const niche of discoveredNiches) {
    const selected = activeFilter === niche.title;
    const card = element('button', `p-3.5 rounded-lg transition text-left space-y-1 border ${selected ? 'border-indigo-500 bg-indigo-950/40' : 'border-zinc-800 bg-zinc-950/80 hover:border-zinc-700'}`);
    card.type = 'button';
    card.setAttribute('aria-pressed', String(selected));
    card.append(element('p', 'text-xs font-semibold text-indigo-300', niche.title),
      element('p', 'text-[11px] text-zinc-400 line-clamp-2', niche.rationale));
    card.addEventListener('click', () => selectNicheFilter(niche.title));
    $('nichesList').append(card);
  }
}
function renderFilteredJobs() {
  const list = $('jobsList');
  list.replaceChildren();
  const jobs = activeFilter === null ? allJobs : allJobs.filter(job => job.niche_category === activeFilter);
  if (!jobs.length) {
    list.append(element('div', 'p-6 border border-zinc-800 rounded-xl text-center text-xs text-zinc-500',
      busy ? 'Searching for matching listings...' : 'No matching listings were extracted. Try another background or Find More if available.'));
  }
  for (const job of jobs) {
    const card = element('article', 'bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4');
    const text = element('div', 'space-y-1.5 flex-1 pr-2');
    text.append(
      element('p', 'text-[10px] font-mono text-indigo-300', `${job.niche_category} · ${job.work_type}`),
      element('h2', 'text-sm font-semibold text-zinc-100', job.job_title),
      element('p', 'text-xs text-zinc-400', `${job.company_name} · ${job.location}`),
      element('p', 'text-xs text-zinc-400 line-clamp-2 leading-relaxed pt-1', job.description),
    );
    card.append(text);
    const href = safeLink(job.apply_url) || safeLink(job.source_url);
    if (href) {
      const link = element('a', 'text-xs bg-zinc-100 text-zinc-950 font-semibold px-4 py-2 rounded-lg whitespace-nowrap', 'Apply Now ↗');
      link.href = href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      card.append(link);
    }
    list.append(card);
  }
}
function targetNiches() {
  return discoveredNiches.filter(niche => (activeFilter === null || activeFilter === niche.title) && progress.get(niche.title)?.has_more);
}
function updateMore() {
  $('findMoreContainer').classList.toggle('hidden', busy || !targetNiches().length);
  $('findMoreBtn').disabled = loadingMore;
  // Preserve the label node across every request.
  $('moreNicheLabel').textContent = loadingMore ? 'Loading...' : activeFilter || 'All Niches';
}
async function fetchMoreForActiveNiche() {
  if (busy || loadingMore) return;
  loadingMore = true;
  $('searchBtn').disabled = true;
  notice('');
  updateMore();
  try {
    for (const niche of targetNiches()) {
      const response = await fetch(`${apiBase}/api/more-jobs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ niche_title: niche.title, search_dork: niche.dork,
          offset: progress.get(niche.title)?.next_offset ?? 0, limit: 2 }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not fetch additional postings.');
      addJobs(data.jobs);
      progress.set(niche.title, data);
      if (data.warnings?.length) notice(data.warnings.join(' '));
    }
  } catch (error) {
    notice(error.message || 'Unable to load more listings. Please retry.');
  } finally {
    loadingMore = false;
    $('searchBtn').disabled = false;
    renderFilteredJobs();
    updateMore();
  }
}
$('searchBtn').addEventListener('click', startDiscovery);
$('showAllBtn').addEventListener('click', () => selectNicheFilter(null));
$('findMoreBtn').addEventListener('click', fetchMoreForActiveNiche);
$('queryInput').addEventListener('keydown', event => { if (event.key === 'Enter') startDiscovery(); });
window.addEventListener('pagehide', () => stream?.close());
