"""Product routes over Nango's own catalog, input schemas, and hosted actions."""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from swarmci.adapters.nango import Nango, NangoError
from swarmci.publishing import Publisher


class Account(BaseModel):
    integration: str
    connection_id: str = ""


class Publish(Account):
    repository: str


class ActionCall(Account):
    name: str
    input: dict = Field(default_factory=dict)


def integration_router(store):
    router = APIRouter(prefix="/api/integrations")
    nango = Nango()
    locks = {}

    @router.get("")
    async def catalog():
        return await nango.catalog()

    @router.get("/templates/{provider}")
    async def templates(provider: str):
        return await nango.sdk("templates", provider=provider)

    @router.get("/functions/{integration}")
    async def functions(integration: str):
        return await nango.sdk("functions", integration=integration)

    @router.post("/connect")
    async def connect(account: Account):
        return await nango.connect(account.integration)

    @router.post("/enable")
    async def enable(body: ActionCall):
        return await nango.sdk("deployment", integration=body.integration, name=body.name)

    @router.post("/destinations")
    async def destinations(account: Account):
        c = await nango.connection(account.integration, account.connection_id)
        return await nango.destinations(c)

    @router.post("/action")
    async def action(body: ActionCall):
        # The UI permits only discovery and issue/report operations, not merges/deletes/admin actions.
        allowed = body.name.startswith(("get-", "list-", "search-")) or body.name in {
            "create-issue",
            "create-ticket",
            "add-issue-comment",
            "create-comment",
            "create-attachment",
        }
        if not allowed:
            raise HTTPException(422, "This action is outside the CI reporting workflow.")
        c = await nango.connection(body.integration, body.connection_id)
        return await nango.action(c, body.name, body.input)

    @router.post("/publish/{run}/{bug}")
    async def publish(run: str, bug: str, body: Publish):
        try:
            snap = store.snapshot(run)
        except KeyError:
            raise HTTPException(404, "Run not found")
        finding = next((b for b in snap["bugs"] if b["id"] == bug), None)
        if not finding:
            raise HTTPException(404, "Verified finding not found")
        c = await nango.connection(body.integration, body.connection_id, "github")
        key = (run, bug, body.repository)
        async with locks.setdefault(key, asyncio.Lock()):
            result = await Publisher(nango).github(snap, finding, c, body.repository)
            store.event(
                run, "finding.published", {"issue": result["issue"], "pr": result["pr"], "provider": "nango"}
            )
            return result

    return router


def install_integrations(app, store):
    from fastapi.responses import JSONResponse

    @app.exception_handler(NangoError)
    async def nango_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    app.include_router(integration_router(store))
