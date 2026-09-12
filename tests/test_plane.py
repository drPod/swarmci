import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from swarmci.browser import BrowserSession
from swarmci.models import Action, Target
from swarmci.plane import PlaneFixture
from swarmci.state import observe


@pytest.mark.asyncio
async def test_portable_references_preserve_values_and_reject_unknown(monkeypatch):
    monkeypatch.setenv("PLANE_FIXTURE_TOKEN", "test-only")
    first = PlaneFixture("http://localhost:8090")
    second = PlaneFixture("http://localhost:8090")
    first.aliases = {"project": "old-project", "workspace_slug": "old-workspace"}
    second.aliases = {"project": "new-project", "workspace_slug": "new-workspace"}
    try:
        action = Action(kind="goto", value="http://localhost:8090/old-workspace/projects/old-project/issues/")
        portable = first.action(action)
        restored = second.action(portable, restore=True)
        assert restored.value.endswith("/new-workspace/projects/new-project/issues/")
        assert first.action(Action(kind="fill", value="Important user text")).value == "Important user text"
        with pytest.raises(ValueError, match="Unknown Plane replay reference"):
            second.expand("{{plane:missing}}")
    finally:
        await first.client.aclose()
        await second.client.aclose()


@pytest.mark.asyncio
async def test_archive_oracle_and_transport_failures(monkeypatch):
    monkeypatch.setenv("PLANE_FIXTURE_TOKEN", "test-only")
    fixture = PlaneFixture("http://localhost:8090")
    fixture.aliases = {"project": "project-id", "workspace_slug": "workspace-slug", "issue_1": "item-id"}

    async def snapshot():
        return {
            "issues": [
                {
                    "id": "{{plane:issue_1}}",
                    "name": "Launch checklist",
                    "archived_at": True,
                    "deleted_at": False,
                }
            ]
        }

    fixture.snapshot = snapshot

    class Response:
        ok = True
        status = 200
        items = []

        async def json(self):
            return {"results": self.items, "next_page_results": False}

    response = Response()

    async def get(url):
        return response

    page = SimpleNamespace(request=SimpleNamespace(get=get))
    try:
        checks = await fixture.checks(page)
        assert len(checks) == 1 and not checks[0]["passed"]
        response.items = [{"id": "item-id"}]
        assert (await fixture.checks(page))[0]["passed"]
        response.ok = False
        response.status = 503
        with pytest.raises(RuntimeError, match="unavailable"):
            await fixture.checks(page)
    finally:
        await fixture.client.aclose()


@pytest.mark.skipif(
    os.environ.get("RUN_PLANE_TESTS") != "1", reason="requires local Plane and fixture broker"
)
@pytest.mark.asyncio
async def test_real_plane_isolation_handoff_and_archive(tmp_path):
    target = Target.model_validate_json(Path("targets/plane.json").read_text())
    async with (
        BrowserSession(target, tmp_path / "first") as first,
        BrowserSession(target, tmp_path / "second") as second,
    ):
        assert first.fixture.aliases["user"] != second.fixture.aliases["user"]
        assert first.fixture.aliases["workspace"] != second.fixture.aliases["workspace"]
        action = Action(kind="click", selector='text="Launch checklist"', label="Open Launch checklist")
        await asyncio.gather(first.act(action), second.act(action))
        a, b = await asyncio.gather(
            observe(first.page, target, [action]), observe(second.page, target, [action])
        )
        assert a["id"] == b["id"], (a["fingerprint_parts"], b["fingerprint_parts"])
        url = first.fixture.expand(
            target.url
            + "/api/workspaces/{{plane:workspace_slug}}/projects/{{plane:project}}/issues/{{plane:issue_1}}/"
        )
        response = await first.page.request.patch(
            url, data={"state": first.fixture.aliases["state_completed"]}
        )
        assert response.ok
        response = await first.page.request.post(url + "archive/")
        assert response.ok
        checks = await first.checks()
        assert len(checks) == 1 and checks[0]["passed"]
        assert await second.checks() == []  # First worker's archive did not change second worker's data.
        changed = await observe(first.page, target, [action])
        assert changed["id"] != b["id"]
        (tmp_path / "results.json").write_text(
            json.dumps({"same_checkpoint": a["id"], "archive_checks": checks})
        )
