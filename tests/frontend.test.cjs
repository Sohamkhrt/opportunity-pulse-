const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { JSDOM } = require('jsdom');

function setup() {
  const dom = new JSDOM(readFileSync('frontend/index.html', 'utf8'), {runScripts: 'outside-only', url: 'https://careers.example.com'});
  const w = dom.window;
  const sources = [];
  w.APP_CONFIG = {apiBaseUrl: 'https://api.example.com'};
  w.EventSource = class {
    constructor(url) { this.url = url; sources.push(this); }
    close() { this.closed = true; }
    emit(data) { this.onmessage({data: JSON.stringify(data)}); }
  };
  w.eval(readFileSync('frontend/app.js', 'utf8'));
  w.document.getElementById('searchBtn').click();
  return {w, source: sources[0], dom};
}
function ready(source) {
  source.emit({type:'niches_ready', niches:[{title:"Engineer's <img src=x onerror=alert(1)>", rationale:'Useful skills', dork:'Robotics'}]});
  source.emit({type:'niche_progress', niche:"Engineer's <img src=x onerror=alert(1)>", next_offset:1, has_more:true});
  source.emit({type:'done', total:0});
}

test('rendering escapes provider content and filters a title with punctuation', () => {
  const {w, source, dom} = setup();
  ready(source);
  assert.equal(w.document.querySelectorAll('#nichesList img').length, 0);
  w.document.querySelector('#nichesList button').click();
  assert.match(w.document.getElementById('moreNicheLabel').textContent, /Engineer's/);
  dom.window.close();
});

test('Find More preserves its label and uses returned offsets on repeated clicks', async () => {
  const {w, source, dom} = setup();
  ready(source);
  const offsets = [];
  w.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    offsets.push(body.offset);
    return {ok:true, json:async () => ({jobs:[], next_offset:body.offset+2, has_more:true})};
  };
  const button = w.document.getElementById('findMoreBtn');
  button.click();
  await new Promise(setImmediate);
  button.click();
  await new Promise(setImmediate);
  assert.deepEqual(offsets, [1,3]);
  assert.ok(w.document.getElementById('moreNicheLabel'));
  assert.equal(button.disabled, false);
  dom.window.close();
});

test('failed pagination retains cursor and presents HTTP error', async () => {
  const {w, source, dom} = setup();
  ready(source);
  const offsets = [];
  w.fetch = async (url, options) => {
    offsets.push(JSON.parse(options.body).offset);
    return {ok:false, json:async () => ({detail:'Server is busy'})};
  };
  w.document.getElementById('findMoreBtn').click();
  await new Promise(setImmediate);
  w.document.getElementById('findMoreBtn').click();
  await new Promise(setImmediate);
  assert.deepEqual(offsets, [1,1]);
  assert.equal(w.document.getElementById('notice').textContent, 'Server is busy');
  dom.window.close();
});

test('SSE errors close the stream and restore controls', () => {
  const {w, source, dom} = setup();
  source.emit({type:'error', message:'Provider unavailable'});
  assert.equal(source.closed, true);
  assert.equal(w.document.getElementById('searchBtn').disabled, false);
  assert.equal(w.document.getElementById('notice').textContent, 'Provider unavailable');
  dom.window.close();
});

test('unsafe application links and HTML are never inserted', () => {
  const {w, source, dom} = setup();
  source.emit({type:'job_found', job:{job_title:'<script>bad()</script>', company_name:'Acme', location:'Remote', description:'<img src=x>', niche_category:'Engineering', work_type:'Remote', apply_url:'javascript:alert(1)', source_url:'data:text/html,bad'}});
  assert.equal(w.document.querySelectorAll('#jobsList script, #jobsList img, #jobsList a').length, 0);
  assert.match(w.document.getElementById('jobsList').textContent, /<script>/);
  dom.window.close();
});
