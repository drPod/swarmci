"""Explicit teardown for the instance IDs created by this project only."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from swarmci.config import settings


async def main():
    path = Path(".secrets/lambda-deployment.json")
    state = json.loads(path.read_text())
    ids = [i["id"] for i in state["instances"]]
    if "--confirm" not in sys.argv:
        print("Would terminate:", *ids)
        print("Run with --confirm to terminate these billable instances.")
        return
    if not ids:
        return
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://cloud.lambda.ai/api/v1/instance-operations/terminate",
            headers={"Authorization": "Bearer " + settings.lambda_api_key},
            json={"instance_ids": ids},
        )
        r.raise_for_status()
        print("Termination requested for", len(ids), "instances")
        state["terminated_instances"] = state.get("terminated_instances", []) + state["instances"]
        state["instances"] = []
        path.write_text(json.dumps(state, indent=2))


asyncio.run(main())
