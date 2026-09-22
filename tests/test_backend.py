import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from backend import main, config
import pipeline


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(main, 'slots', asyncio.Semaphore(2))
    monkeypatch.setattr(main, 'require_configuration', lambda: None)
    monkeypatch.setitem(pipeline.COLLECTORS, 'jobs.lever.co', 'test-collector')


def client():
    return TestClient(main.app)


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def test_health_and_static_assets():
    with client() as c:
        assert c.get('/healthz').json() == {'status': 'ok'}
        assert c.get('/').status_code == 200
        assert 'apiBaseUrl' in c.get('/config.js').text
        assert c.get('/.env').status_code == 404
        assert c.get('/api/jobs').json() == []


def test_stream_success(monkeypatch):
    async def discover(query):
        assert query == 'engineer'
        yield {'type': 'job_found', 'job': {'job_title': 'Engineer'}}
        yield {'type': 'done', 'total': 1}
    monkeypatch.setattr(main, 'stream_niche_discovery', discover)
    response = client().get('/api/stream-discover', params={'query': 'engineer'})
    assert [e['type'] for e in events(response)] == ['job_found', 'done']
    assert response.headers['x-accel-buffering'] == 'no'
    assert main.slots._value == 2


def test_stream_provider_error_and_slot_release(monkeypatch):
    async def broken(query):
        raise config.ProviderError('Provider unavailable')
        yield
    monkeypatch.setattr(main, 'stream_niche_discovery', broken)
    response = client().get('/api/stream-discover?query=engineer')
    assert events(response) == [{'type': 'error', 'message': 'Provider unavailable'}]
    assert main.slots._value == 2


def test_stream_cancellation_cancels_work(monkeypatch):
    async def run():
        stopped = asyncio.Event()
        async def slow(query):
            try:
                await asyncio.sleep(3600)
                yield {'type': 'done'}
            finally:
                stopped.set()
        monkeypatch.setattr(main, 'stream_niche_discovery', slow)
        response = await main.stream_discover('engineer')
        body = response.body_iterator
        assert await anext(body) == ': connected\n\n'
        task = asyncio.create_task(anext(body))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
        assert main.slots._value == 2
    asyncio.run(run())


def test_busy_stream(monkeypatch):
    monkeypatch.setattr(main, 'slots', asyncio.Semaphore(0))
    assert events(client().get('/api/stream-discover?query=engineer'))[0]['type'] == 'error'


def test_missing_configuration(monkeypatch):
    def missing():
        raise config.ProviderError('Missing server configuration')
    monkeypatch.setattr(main, 'require_configuration', missing)
    assert events(client().get('/api/stream-discover?query=engineer'))[0]['message'] == 'Missing server configuration'
    assert client().post('/api/more-jobs', json={'niche_title': 'Engineer'}).status_code == 503


@pytest.mark.parametrize('body', [
    {'niche_title': ' '}, {'niche_title': 'Engineer', 'offset': -1},
    {'niche_title': 'Engineer', 'limit': 100}, {'niche_title': 'Engineer', 'search_dork': 'x' * 301},
])
def test_validation(body):
    assert client().post('/api/more-jobs', json=body).status_code == 422


def test_more_jobs_returns_cursor(monkeypatch):
    result = {'jobs': [], 'next_offset': 3, 'has_more': True, 'warnings': []}
    provider = AsyncMock(return_value=result)
    monkeypatch.setattr(main, 'fetch_more_jobs', provider)
    response = client().post('/api/more-jobs', json={'niche_title': 'Engineer', 'offset': 1})
    assert response.json()['next_offset'] == 3
    provider.assert_awaited_once_with(niche_title='Engineer', search_dork='', offset=1, limit=2)


def test_pipeline_skips_invalid_records_and_advances(monkeypatch):
    urls = [f'https://jobs.lever.co/company/{i}' for i in range(4)]
    monkeypatch.setattr(pipeline, 'search_urls', AsyncMock(return_value=urls))
    extract = AsyncMock(side_effect=[None, {'source_url': urls[2]}])
    monkeypatch.setattr(pipeline, 'extract_job', extract)
    result = asyncio.run(pipeline.fetch_more_jobs('Engineer', '', 1, 2))
    assert result['next_offset'] == 3
    assert result['has_more'] is True
    assert len(result['jobs']) == 1
    assert result['warnings']
    assert extract.await_args_list[0].args[0] == urls[1]


def test_search_deduplicates_and_rejects_unconfigured_hosts(monkeypatch):
    monkeypatch.setitem(pipeline.COLLECTORS, 'jobs.ashbyhq.com', '')
    monkeypatch.setattr(pipeline, 'bdata_exec', AsyncMock(return_value={'organic': [
        {'link': 'https://jobs.lever.co/acme/1'},
        {'link': 'https://jobs.lever.co/acme/1/apply'},
        {'link': 'https://jobs.lever.co.evil.test/acme/2'},
        {'link': 'https://jobs.ashbyhq.com/acme/3'},
    ]}))
    assert asyncio.run(pipeline.search_urls('engineer')) == ['https://jobs.lever.co/acme/1']


def test_cli_passes_untrusted_text_as_one_argument(monkeypatch):
    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (b'{"organic": []}', b'')
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(pipeline.asyncio, 'create_subprocess_exec', spawn)
    query = 'engineer & echo unwanted'
    asyncio.run(pipeline.bdata_exec('search', query))
    assert spawn.call_args.args[-3:] == ('search', query, '--json')
    assert 'shell' not in spawn.call_args.kwargs


def test_cors_exact_origins(monkeypatch):
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi import FastAPI
    monkeypatch.setenv('CORS_ORIGINS', 'https://careers.example.com')
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_methods=['POST'], allow_headers=['Content-Type'])
    c = TestClient(app)
    headers = {'Origin': 'https://careers.example.com', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type'}
    assert c.options('/api/more-jobs', headers=headers).headers['access-control-allow-origin'] == headers['Origin']
    headers['Origin'] = 'https://untrusted.example.com'
    assert 'access-control-allow-origin' not in c.options('/api/more-jobs', headers=headers).headers
    monkeypatch.setenv('CORS_ORIGINS', '*')
    with pytest.raises(ValueError):
        config.cors_origins()


def test_full_discovery_and_more_jobs_contract(monkeypatch):
    pivots = [{'niche_title': f'Niche {i}', 'rationale': 'Transferable skills', 'search_dork': 'Robotics'} for i in range(4)]
    monkeypatch.setattr(pipeline, 'expand_niche_ideas_llm', AsyncMock(return_value=pivots))
    async def provider(*args):
        if args[0] == 'search':
            return {'organic': [{'link': f'https://jobs.lever.co/acme/{i}'} for i in range(3)]}
        return [{'job_title': 'Robotics Engineer', 'company_name': 'Acme', 'location': 'Remote',
                 'description': 'Build and maintain robotic systems in challenging field environments.'}]
    monkeypatch.setattr(pipeline, 'bdata_exec', provider)
    result = events(client().get('/api/stream-discover?query=engineer'))
    assert result[0]['type'] == 'niches_ready'
    assert result[-1] == {'type': 'done', 'total': 4}
    assert len([event for event in result if event['type'] == 'job_found']) == 4
    cursors = [event for event in result if event['type'] == 'niche_progress']
    assert all(event['next_offset'] == 1 and event['has_more'] for event in cursors)
    more = client().post('/api/more-jobs', json={'niche_title': 'Niche 0', 'offset': 1, 'limit': 2}).json()
    assert [job['source_url'] for job in more['jobs']] == ['https://jobs.lever.co/acme/1', 'https://jobs.lever.co/acme/2']
    assert more['next_offset'] == 3
    assert more['has_more'] is False


def test_stream_deadline_cleans_up(monkeypatch):
    closed = []
    async def slow(query):
        try:
            await asyncio.sleep(100)
            yield {'type': 'done'}
        finally:
            closed.append(True)
    monkeypatch.setattr(main, 'stream_niche_discovery', slow)
    monkeypatch.setattr(main, 'DISCOVERY_TIMEOUT', .01)
    response = client().get('/api/stream-discover?query=engineer')
    assert events(response)[0]['type'] == 'error'
    assert 'timed out' in events(response)[0]['message']
    assert closed == [True]
    assert main.slots._value == 2
