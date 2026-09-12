"""Exercise the real SDK in a fresh process (its OTel provider is process-global)."""

import os
import subprocess
import sys


def test_sdk_export_concurrency_errors_and_model_usage():
    script = r"""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx
from openai import AsyncOpenAI
from swarmci.adapters import tracing
from swarmci.config import settings

received = []
class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        assert self.path == '/api/v2/traces'
        received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{}')
server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
settings.respan_api_key = ''
assert tracing.initialize() is None
with tracing.span('disabled') as s:
    assert not s.is_recording()
settings.respan_api_key = 'local-test-only'
settings.respan_base_url = f'http://127.0.0.1:{server.server_port}/api'
settings.respan_endpoint = ''
first = tracing.initialize()
assert first is not None and tracing.initialize() is first

async def worker(index):
    with tracing.span('job', job_id=str(index)):
        await asyncio.sleep(0.01)
        with tracing.span('action', action_kind='click'):
            await asyncio.sleep(0)
        if index == 1:
            try:
                with tracing.span('failure'):
                    raise ValueError('controlled failure')
            except ValueError:
                pass
        if index == 2:
            try:
                with tracing.span('cancel'):
                    raise asyncio.CancelledError()
            except asyncio.CancelledError:
                pass

async def run():
    with tracing.span('run', kind='workflow', run_id='test-run'):
        await asyncio.gather(*(worker(i) for i in range(3)))
        def respond(request):
            return httpx.Response(200, json={
                'id':'test', 'object':'chat.completion', 'created':1, 'model':'gemma-test',
                'choices':[{'index':0, 'message':{'role':'assistant','content':'[]'}, 'finish_reason':'stop'}],
                'usage':{'prompt_tokens':7,'completion_tokens':2,'total_tokens':9},
            })
        async with AsyncOpenAI(api_key='provider-secret', base_url='http://model.test/v1',
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            await client.chat.completions.create(model='gemma-test', messages=[{'role':'user','content':'test'}])
asyncio.run(run())
with tracing.span('api-request', run_id='request'):
    with tracing.span('background-run', root=True, run_id='background'):
        pass
tracing.flush()
tracing.shutdown()
server.shutdown()
thread.join()
spans = [s for p in received for r in p['resourceSpans'] for scope in r['scopeSpans'] for s in scope['spans']]
assert len(spans) == 12, [(s['name'], s.get('attributes')) for s in spans]
def attrs(s):
    return {a['key']: next(iter(a['value'].values())) for a in s.get('attributes', [])}
root = next(s for s in spans if s['name'].startswith('run'))
jobs = [s for s in spans if s['name'].startswith('job')]
assert len(jobs) == 3
assert all(s['traceId'] == root['traceId'] for s in spans if s['name'] not in ('api-request', 'background-run'))
background = next(s for s in spans if s['name'] == 'background-run')
request = next(s for s in spans if s['name'] == 'api-request')
assert background['traceId'] != request['traceId']
assert not background.get('parentSpanId')
assert all(s['parentSpanId'] == root['spanId'] for s in jobs)
assert {attrs(s)['job_id'] for s in jobs} == {'0','1','2'}
for job in jobs:
    action = next(s for s in spans if s['name'].startswith('action') and s['parentSpanId'] == job['spanId'])
    assert attrs(action)['respan.metadata.job_id'] == attrs(job)['job_id']
failure = next(s for s in spans if s['name'].startswith('failure'))
assert failure['status']['code'] == 2
cancel = next(s for s in spans if s['name'].startswith('cancel'))
assert attrs(cancel)['outcome'] == 'cancelled'
llm = next(s for s in spans if s['name'] == 'LLM · gemma-test')
assert any(str(v) == '7' for k,v in attrs(llm).items() if 'token' in k), attrs(llm)
assert all(attrs(s)['respan.metadata.run_id'] == 'test-run' for s in spans if s['name'] not in ('api-request', 'background-run'))
assert attrs(llm)['respan.metadata.run_id'] == 'test-run'
assert 'provider-secret' not in json.dumps(received)
print('SDK JSON export, hierarchy, concurrency, cancellation, errors, and model usage verified')
"""
    env = {**os.environ, "RESPAN_ENABLED": "true", "RESPAN_API_KEY": ""}
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
