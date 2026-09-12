import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from swarmci.browser import BrowserSession
from swarmci.config import settings
from swarmci.models import Action, RunConfig, Target
from swarmci.runner import Coordinator, replay_manifest
from swarmci.state import observe
from swarmci.store import Store


@pytest.fixture
def fixture_url():
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = partial(QuietHandler, directory=str(Path("swarmci/static").resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/fixture.html"
    server.shutdown()
    thread.join()


@pytest.fixture
def target(fixture_url):
    data = json.loads(Path("targets/fixture.json").read_text())
    data["url"] = fixture_url
    return Target.model_validate(data)


async def test_swarm_verifies_bug_and_ci_passes_fix(tmp_path, monkeypatch, target):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    store = Store(tmp_path / "db")
    c = Coordinator(store)
    cfg = RunConfig(target=target, engine="fixture", workers=3, max_jobs=25, budget_seconds=90)
    id = store.create_run(cfg)
    await c.run(id, cfg)
    snap = store.snapshot(id)
    assert snap["status"] == "completed", snap["jobs"]
    assert snap["metrics"]["handoffs"] > 0
    assert snap["metrics"]["converging_states"] > 0
    assert len(snap["bugs"]) == 1
    bug = snap["bugs"][0]
    assert bug["steps"] == 4
    assert all(Path(v).stat().st_size > 1000 for v in bug["videos"])
    broken = await replay_manifest(Path(bug["replay"]), tmp_path / "broken")
    assert broken["status"] == "failed"
    fixed = await replay_manifest(Path(bug["replay"]), tmp_path / "fixed", target.url + "?fixed=1")
    assert fixed["status"] == "passed", fixed
    assert (tmp_path / "fixed" / "junit.xml").exists()


async def test_identical_screens_with_different_hierarchy_do_not_merge(tmp_path, target):
    async with BrowserSession(target, tmp_path / "browser") as session:
        first = await observe(session.page, target, [])
        action = Action(kind="click", selector="[data-testid=group]")
        await session.act(action)
        grouped = await observe(session.page, target, [action])
        assert first["id"] != grouped["id"]
        assert first["app_key"] != grouped["app_key"]


async def test_no_assertions_is_runner_error(tmp_path, target):
    target.assertions = []
    target.failure_selector = ""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"version": 1, "target": target.model_dump(), "actions": [], "assertions": []})
    )
    result = await replay_manifest(manifest, tmp_path / "out")
    assert result["status"] == "error"


async def test_browser_use_hooks_record_replayable_action(tmp_path, target, monkeypatch):
    """Real BU + real Chromium; only model inference is scripted for offline CI."""
    import browser_use
    from browser_use.llm.views import ChatInvokeCompletion

    from swarmci.agents import explore_bu

    class ScriptedModel:
        model = "scripted-offline-test"
        provider = "test"
        name = "scripted-offline-test"
        model_name = "scripted-offline-test"
        _verified_api_keys = True

        async def ainvoke(self, messages, output_format=None, **kwargs):
            obj = {
                "thinking": "Click the group button for the adapter smoke test.",
                "evaluation_previous_goal": "Starting the controlled test",
                "memory": "Controlled test",
                "next_goal": "Click group",
                "action": [{"click": {"coordinate_x": 1300, "coordinate_y": 157}}],
            }
            return ChatInvokeCompletion(completion=output_format.model_validate(obj), usage=None)

    monkeypatch.setattr(browser_use, "ChatOpenAI", lambda **kwargs: ScriptedModel())
    recorded = []

    async def record(action):
        recorded.append(action)
        return False

    async with BrowserSession(target, tmp_path / "bu") as session:
        await explore_bu(session, target, "Click Add intermediate group", 3, record, tmp_path / "bu")
        assert recorded and recorded[0].kind == "click"
        assert await session.page.evaluate("window.__swarmState().group")
    async with BrowserSession(target, tmp_path / "replay") as session:
        await session.replay(recorded)
        assert await session.page.evaluate("window.__swarmState().group")


async def test_replay_locator_survives_unrelated_dom_insertion(tmp_path):
    from swarmci.agents import REPLAY_SELECTORS
    target = Target(name='Locator regression', url='about:blank')
    async with BrowserSession(target, tmp_path / 'locators') as session:
        await session.page.set_content('<main><a href="/items/one"><button>Status</button></a></main>')
        addresses = await session.page.evaluate(REPLAY_SELECTORS, [[1, '/html/body/main/a/button']])
        assert addresses['1'] == 'a[href="/items/one"] button'
        await session.page.evaluate("document.querySelector('main').prepend(document.createElement('div'))")
        await session.page.locator(addresses['1']).click(no_wait_after=True)


async def test_document_oracle_checks_main_frame_and_replays(tmp_path, fixture_url):
    from swarmci.models import Assertion
    target = Target(name='Navigation check', url=fixture_url,
                    assertions=[Assertion(name='Destination loads successfully', kind='document_status')])
    async with BrowserSession(target, tmp_path / 'navigation') as session:
        assert (await session.checks())[0]['passed']
        # An unrelated resource failure does not make the document fail.
        await session.page.request.get(fixture_url + '.missing')
        assert (await session.checks())[0]['passed']
        await session.page.goto(fixture_url + '.missing')
        checks = await session.checks()
        assert not checks[0]['passed'] and checks[0]['observed']['status'] == 404
        await session.page.evaluate("history.pushState({}, '', '/client-route')")
        assert await session.checks() == []
